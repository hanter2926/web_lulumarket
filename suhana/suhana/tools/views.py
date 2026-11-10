import json
import math
import logging

from django.http import FileResponse, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from .models import ComparisonJob, ComparisonReport
from .processing_jobs import (
    ComparisonJobAccessError,
    ComparisonJobExpired,
    ComparisonQueueFull,
    authorized_job,
    cancel_comparison_job,
    compression_output_path,
    enqueue_compression,
    enqueue_comparison,
)
from .rust_engine import ProcessingEngineError


logger = logging.getLogger(__name__)

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
    except Exception:
        logger.exception("Comparison request could not be queued.")
        return JsonResponse(
            {
                "success": False,
                "message": "The comparison could not be started. Please try again.",
            },
            status=500,
        )

    status_url = f"/api/tools/jobs/{job.id}/"
    response = _job_response(job)
    response.update(
        {
            "job_token": token,
            "status_url": status_url,
            "cancel_url": f"{status_url}cancel/",
        }
    )
    return JsonResponse(response, status=202)


@require_POST
def compress_file(request):
    upload = request.FILES.get("file")
    if upload is None:
        return JsonResponse(
            {"success": False, "message": "Choose a file to compress."}, status=400
        )

    try:
        job, token = enqueue_compression(request, upload, request.POST)
    except ComparisonQueueFull as error:
        return JsonResponse({"success": False, "message": str(error)}, status=429)
    except ProcessingEngineError as error:
        return JsonResponse({"success": False, "message": str(error)}, status=503)
    except ValueError as error:
        return JsonResponse({"success": False, "message": str(error)}, status=400)

    status_url = f"/api/tools/jobs/{job.id}/"
    response = _job_response(job)
    response.update(
        {
            "job_token": token,
            "status_url": status_url,
            "cancel_url": f"{status_url}cancel/",
        }
    )
    return JsonResponse(response, status=202)


def _job_response(job):
    processing_label = (
        "Compression"
        if job.job_type == ComparisonJob.Type.COMPRESSION
        else "Comparison"
    )
    lifecycle = {
        ComparisonJob.Status.QUEUED: ("queued", "Waiting for a worker."),
        ComparisonJob.Status.RUNNING: (
            "processing",
            "Compressing file." if processing_label == "Compression" else "Comparing files.",
        ),
        ComparisonJob.Status.SUCCEEDED: ("completed", f"{processing_label} completed."),
        ComparisonJob.Status.FAILED: ("failed", f"{processing_label} failed."),
        ComparisonJob.Status.CANCELLED: ("cancelled", f"{processing_label} cancelled."),
    }
    state, stage = lifecycle[job.status]
    response = {
        "success": job.status not in {ComparisonJob.Status.FAILED},
        "job_id": str(job.id),
        "status": job.status,
        "state": state,
        "stage": stage,
        "cancel_requested": job.cancel_requested,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
    if job.status == ComparisonJob.Status.SUCCEEDED:
        if job.job_type == ComparisonJob.Type.COMPRESSION:
            response["compression"] = job.result
            response["download_url"] = f"/api/tools/jobs/{job.id}/download/"
        else:
            response["comparison"] = job.result
            response["report_id"] = job.report_id
    elif job.status == ComparisonJob.Status.FAILED:
        response["message"] = job.error
    return response


@require_GET
@never_cache
def compression_download(request, job_id):
    try:
        job = authorized_job(request, job_id)
    except ComparisonJobAccessError:
        return JsonResponse({"success": False, "message": "Job not found."}, status=404)
    except ComparisonJobExpired:
        return JsonResponse({"success": False, "message": "Job has expired."}, status=410)
    if (
        job.job_type != ComparisonJob.Type.COMPRESSION
        or job.status != ComparisonJob.Status.SUCCEEDED
        or not isinstance(job.result, dict)
    ):
        return JsonResponse(
            {"success": False, "message": "Compressed output is not available."},
            status=409,
        )
    try:
        output_path = compression_output_path(job.id)
        response = FileResponse(
            output_path.open("rb"),
            as_attachment=True,
            filename=job.result["filename"],
            content_type=job.result["content_type"],
        )
    except (OSError, KeyError, ValueError):
        logger.exception("Compressed output is unavailable for job %s.", job.id)
        return JsonResponse(
            {"success": False, "message": "The compressed output is unavailable."},
            status=410,
        )
    response["Cache-Control"] = "private, no-store"
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
