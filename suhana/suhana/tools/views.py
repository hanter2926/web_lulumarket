import json
import math

from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from .models import ComparisonJob, ComparisonReport
from .processing_jobs import (
    ComparisonJobAccessError,
    ComparisonJobExpired,
    ComparisonQueueFull,
    authorized_job,
    cancel_comparison_job,
    enqueue_comparison,
)
from .rust_engine import ProcessingEngineError


UNIT_FACTORS = {
    "bit": 1,
    "byte": 8,
    "kb": 8 * 1000,
    "mb": 8 * 1000**2,
    "gb": 8 * 1000**3,
    "tb": 8 * 1000**4,
}


def _json_body(request):
    try:
        value = json.loads(request.body or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return value if isinstance(value, dict) else None


@require_POST
def convert_units(request):
    data = _json_body(request)
    if data is None:
        return JsonResponse({"success": False, "message": "Invalid JSON data."}, status=400)

    try:
        value = float(data.get("value"))
        source = str(data.get("from", "")).lower()
        target = str(data.get("to", "")).lower()
    except (TypeError, ValueError):
        return JsonResponse(
            {"success": False, "message": "Enter a valid numeric value."}, status=400
        )

    if (
        not math.isfinite(value)
        or value < 0
        or source not in UNIT_FACTORS
        or target not in UNIT_FACTORS
    ):
        return JsonResponse(
            {"success": False, "message": "Invalid unit or value."}, status=400
        )

    result = value * UNIT_FACTORS[source] / UNIT_FACTORS[target]
    return JsonResponse(
        {"success": True, "value": value, "from": source, "to": target, "result": result}
    )


@require_POST
def compare_files(request):
    first = request.FILES.get("first")
    second = request.FILES.get("second")
    if first is None or second is None:
        return JsonResponse(
            {"success": False, "message": "Upload both files to compare."}, status=400
        )

    try:
        job, token = enqueue_comparison(request, first, second)
    except ComparisonQueueFull as error:
        return JsonResponse({"success": False, "message": str(error)}, status=429)
    except ProcessingEngineError as error:
        return JsonResponse({"success": False, "message": str(error)}, status=503)
    except ValueError as error:
        return JsonResponse({"success": False, "message": str(error)}, status=400)

    status_url = f"/api/tools/jobs/{job.id}/"
    return JsonResponse(
        {
            "success": True,
            "job_id": str(job.id),
            "job_token": token,
            "status": job.status,
            "status_url": status_url,
            "cancel_url": f"{status_url}cancel/",
        },
        status=202,
    )


def _job_response(job):
    response = {
        "success": job.status not in {ComparisonJob.Status.FAILED},
        "job_id": str(job.id),
        "status": job.status,
        "cancel_requested": job.cancel_requested,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
    if job.status == ComparisonJob.Status.SUCCEEDED:
        response["comparison"] = job.result
        response["report_id"] = job.report_id
    elif job.status == ComparisonJob.Status.FAILED:
        response["message"] = job.error
    return response


@require_GET
@never_cache
def comparison_job_status(request, job_id):
    try:
        job = authorized_job(request, job_id)
    except ComparisonJobAccessError:
        return JsonResponse({"success": False, "message": "Job not found."}, status=404)
    except ComparisonJobExpired:
        return JsonResponse({"success": False, "message": "Job has expired."}, status=410)
    return JsonResponse(_job_response(job))


@require_POST
def cancel_comparison(request, job_id):
    try:
        job = authorized_job(request, job_id)
    except ComparisonJobAccessError:
        return JsonResponse({"success": False, "message": "Job not found."}, status=404)
    except ComparisonJobExpired:
        return JsonResponse({"success": False, "message": "Job has expired."}, status=410)

    job = cancel_comparison_job(job.id)
    response = _job_response(job)
    return JsonResponse(response)


@require_GET
@never_cache
def reports(request):
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "message": "Authentication required."}, status=401)
    return JsonResponse({
        "success": True,
        "reports": list(ComparisonReport.objects.filter(owner=request.user).values(
            "id", "first_name", "second_name", "comparison_type", "result", "created_at"
        )),
    })
