import hashlib
from pathlib import PurePath

from django.db import IntegrityError, transaction
from django.http import FileResponse, JsonResponse
from django.views.decorators.http import require_GET, require_POST

from tools.models import ComparisonJob, ComparisonReport

from .models import Folder, StoredFile, UserStorage

MAX_STORAGE_FILE_SIZE = 25 * 1024 * 1024


def _auth_error(request):
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "message": "Authentication required."}, status=401)
    return None


@require_GET
def dashboard(request):
    error = _auth_error(request)
    if error:
        return error
    storage = UserStorage.objects.select_related("plan").filter(user=request.user).first()
    files = StoredFile.objects.filter(owner=request.user)
    comparisons = ComparisonReport.objects.filter(owner=request.user).order_by("-created_at").values(
        "first_name", "second_name", "created_at"
    )[:10]
    compressions = ComparisonJob.objects.filter(
        owner=request.user,
        job_type=ComparisonJob.Type.COMPRESSION,
        status=ComparisonJob.Status.SUCCEEDED,
    ).order_by("-created_at").values("first_name", "created_at")[:10]
    activities = [
        {
            "type": "comparison",
            "description": f"{item['first_name']} compared with {item['second_name']}",
            "created_at": item["created_at"].isoformat(),
        }
        for item in comparisons
    ] + [
        {
            "type": "compression",
            "description": f"Compressed {item['first_name']}",
            "created_at": item["created_at"].isoformat(),
        }
        for item in compressions
    ]
    activities.sort(key=lambda activity: activity["created_at"], reverse=True)
    return JsonResponse(
        {
            "success": True,
            "username": request.user.get_username(),
            "file_count": files.count(),
            "storage": None
            if storage is None
            else {
                "used_bytes": storage.used_bytes,
                "quota_bytes": storage.plan.quota_bytes,
                "available_bytes": storage.available_bytes,
                "plan": storage.plan.name,
            },
            "recent_files": list(
                files.values("id", "name", "size_bytes", "content_type", "updated_at")[:10]
            ),
            "recent_activities": activities[:10],
        }
    )


@require_GET
def list_files(request):
    error = _auth_error(request)
    if error:
        return error
    folder_id = request.GET.get("folder")
    files = StoredFile.objects.filter(owner=request.user)
    if folder_id:
        files = files.filter(folder_id=folder_id)
    return JsonResponse({"success": True, "files": list(files.values(
        "id", "name", "size_bytes", "content_type", "folder_id", "created_at"
    ))})


@require_GET
def list_folders(request):
    error = _auth_error(request)
    if error:
        return error
    return JsonResponse({"success": True, "folders": list(
        Folder.objects.filter(owner=request.user).values("id", "name", "parent_id")
    )})


@require_POST
def create_folder(request):
    error = _auth_error(request)
    if error:
        return error
    name = str(request.POST.get("name", "")).strip()
    if not name or len(name) > 255:
        return JsonResponse({"success": False, "message": "A valid folder name is required."}, status=400)
    parent = None
    parent_id = request.POST.get("parent")
    if parent_id:
        parent = Folder.objects.filter(id=parent_id, owner=request.user).first()
        if parent is None:
            return JsonResponse({"success": False, "message": "Parent folder not found."}, status=404)
    folder, created = Folder.objects.get_or_create(owner=request.user, parent=parent, name=name)
    return JsonResponse({"success": True, "created": created, "folder_id": folder.id}, status=201 if created else 200)


@require_POST
def rename_folder(request, folder_id):
    error = _auth_error(request)
    if error:
        return error
    folder = Folder.objects.filter(id=folder_id, owner=request.user).first()
    if folder is None:
        return JsonResponse({"success": False, "message": "Folder not found."}, status=404)
    name = str(request.POST.get("name", "")).strip()
    if not name or len(name) > 255:
        return JsonResponse({"success": False, "message": "A valid folder name is required."}, status=400)
    folder.name = name
    try:
        folder.save(update_fields=["name", "updated_at"])
    except IntegrityError:
        return JsonResponse({"success": False, "message": "A folder with that name already exists."}, status=409)
    return JsonResponse({"success": True, "message": "Folder renamed."})


@require_POST
def delete_folder(request, folder_id):
    error = _auth_error(request)
    if error:
        return error
    with transaction.atomic():
        folder = Folder.objects.filter(id=folder_id, owner=request.user).first()
        if folder is None:
            return JsonResponse({"success": False, "message": "Folder not found."}, status=404)
        storage = UserStorage.objects.select_for_update().filter(user=request.user).first()
        folder_ids = [folder.id]
        pending_ids = [folder.id]
        while pending_ids:
            child_ids = list(
                Folder.objects.filter(owner=request.user, parent_id__in=pending_ids)
                .values_list("id", flat=True)
            )
            folder_ids.extend(child_ids)
            pending_ids = child_ids
        stored_files = StoredFile.objects.filter(
            owner=request.user, folder_id__in=folder_ids
        )
        released = sum(stored_files.values_list("size_bytes", flat=True))
        if storage:
            storage.used_bytes = max(storage.used_bytes - released, 0)
            storage.save(update_fields=["used_bytes"])
        for stored in stored_files:
            stored.file.delete(save=False)
        folder.delete()
    return JsonResponse({"success": True, "message": "Folder deleted."})


@require_POST
def upload_file(request):
    error = _auth_error(request)
    if error:
        return error
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return JsonResponse({"success": False, "message": "Choose a file to upload."}, status=400)
    if uploaded.size > MAX_STORAGE_FILE_SIZE:
        return JsonResponse(
            {"success": False, "message": "Each stored file must be 25 MB or smaller."},
            status=413,
        )
    safe_name = PurePath(uploaded.name or "").name.strip()
    if not safe_name or safe_name in {".", ".."} or len(safe_name) > 255:
        return JsonResponse({"success": False, "message": "The file name is invalid."}, status=400)
    content_type = uploaded.content_type or "application/octet-stream"
    if any(ord(character) < 32 or ord(character) == 127 for character in content_type):
        content_type = "application/octet-stream"

    folder = None
    folder_id = request.POST.get("folder")
    if folder_id:
        folder = Folder.objects.filter(id=folder_id, owner=request.user).first()
        if folder is None:
            return JsonResponse({"success": False, "message": "Folder not found."}, status=404)

    with transaction.atomic():
        storage = UserStorage.objects.select_for_update().select_related("plan").filter(
            user=request.user
        ).first()
        if storage is None:
            return JsonResponse({"success": False, "message": "Storage is not configured for this account."}, status=409)
        if not storage.can_store(uploaded.size):
            return JsonResponse({"success": False, "message": "Storage quota exceeded."}, status=413)

        digest = hashlib.sha256()
        for chunk in uploaded.chunks():
            digest.update(chunk)
        uploaded.seek(0)
        stored = StoredFile.objects.create(
            owner=request.user,
            folder=folder,
            name=safe_name,
            file=uploaded,
            size_bytes=uploaded.size,
            content_type=content_type,
            sha256=digest.hexdigest(),
        )
        storage.used_bytes += uploaded.size
        storage.save(update_fields=["used_bytes"])

    return JsonResponse({"success": True, "file_id": stored.id}, status=201)


@require_GET
def download_file(request, file_id):
    error = _auth_error(request)
    if error:
        return error
    stored = StoredFile.objects.filter(id=file_id, owner=request.user).first()
    if stored is None:
        return JsonResponse({"success": False, "message": "File not found."}, status=404)
    response = FileResponse(stored.file.open("rb"), as_attachment=True, filename=stored.name)
    if stored.content_type:
        response["Content-Type"] = stored.content_type
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_POST
def rename_file(request, file_id):
    error = _auth_error(request)
    if error:
        return error
    stored = StoredFile.objects.filter(id=file_id, owner=request.user).first()
    if stored is None:
        return JsonResponse({"success": False, "message": "File not found."}, status=404)
    name = str(request.POST.get("name", "")).strip()
    if (
        not name
        or len(name) > 255
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
    ):
        return JsonResponse({"success": False, "message": "A valid file name is required."}, status=400)
    stored.name = name
    try:
        with transaction.atomic():
            stored.save(update_fields=["name", "updated_at"])
    except IntegrityError:
        return JsonResponse({"success": False, "message": "A file with that name already exists in this folder."}, status=409)
    return JsonResponse({"success": True, "message": "File renamed."})


@require_POST
def move_file(request, file_id):
    error = _auth_error(request)
    if error:
        return error
    stored = StoredFile.objects.filter(id=file_id, owner=request.user).first()
    if stored is None:
        return JsonResponse({"success": False, "message": "File not found."}, status=404)
    folder_id = request.POST.get("folder", "").strip()
    folder = None
    if folder_id:
        folder = Folder.objects.filter(id=folder_id, owner=request.user).first()
        if folder is None:
            return JsonResponse({"success": False, "message": "Destination folder not found."}, status=404)
    stored.folder = folder
    try:
        with transaction.atomic():
            stored.save(update_fields=["folder", "updated_at"])
    except IntegrityError:
        return JsonResponse({"success": False, "message": "A file with that name already exists in the destination folder."}, status=409)
    return JsonResponse({"success": True, "message": "File moved."})


@require_POST
def delete_file(request, file_id):
    error = _auth_error(request)
    if error:
        return error
    with transaction.atomic():
        stored = StoredFile.objects.filter(id=file_id, owner=request.user).first()
        if stored is None:
            return JsonResponse({"success": False, "message": "File not found."}, status=404)
        storage = UserStorage.objects.select_for_update().filter(user=request.user).first()
        if storage:
            storage.used_bytes = max(storage.used_bytes - stored.size_bytes, 0)
            storage.save(update_fields=["used_bytes"])
        stored.file.delete(save=False)
        stored.delete()
    return JsonResponse({"success": True, "message": "File deleted."})
