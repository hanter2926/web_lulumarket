import json

from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .comparison import compare_uploads


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

    if value < 0 or source not in UNIT_FACTORS or target not in UNIT_FACTORS:
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
        result = compare_uploads(first, second)
    except ValueError as error:
        return JsonResponse({"success": False, "message": str(error)}, status=400)

    return JsonResponse({"success": True, "comparison": result})
