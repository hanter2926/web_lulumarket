import hashlib

from django.db import transaction
from django.http import FileResponse, JsonResponse
from django.views.decorators.http import require_GET, require_POST

from .models import Folder, StoredFile, UserStorage


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
                "plan": storage.plan.name,
            },
            "recent_files": list(
                files.values("id", "name", "size_bytes", "content_type", "updated_at")[:10]
            ),
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
def upload_file(request):
    error = _auth_error(request)
    if error:
        return error
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return JsonResponse({"success": False, "message": "Choose a file to upload."}, status=400)

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
            name=uploaded.name,
            file=uploaded,
            size_bytes=uploaded.size,
            content_type=uploaded.content_type or "",
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
    return response


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
