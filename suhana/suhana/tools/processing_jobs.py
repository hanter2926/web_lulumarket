import hashlib
import hmac
import logging
import os
import secrets
import shutil
import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.utils import timezone

from .comparison import (
    MAX_COMPARISON_FILE_SIZE,
    SUPPORTED_CONTENT_TYPES,
    SUPPORTED_PDF_TYPE,
    detect_content_type,
    _validate_signature,
    compare_uploads,
)
from .models import ComparisonJob, ComparisonQueueControl, ComparisonReport
from .rust_engine import (
    ProcessingCancelledError,
    ProcessingEngineError,
    cancellation_check,
    compress_image,
    compress_pdf,
)


logger = logging.getLogger(__name__)

MAX_ACTIVE_COMPARISON_JOBS = 100
MAX_CONCURRENT_COMPARISON_JOBS = 2
MAX_ACTIVE_JOBS_PER_OWNER = 3
MAX_ACTIVE_JOBS_PER_CLIENT = 3
COMPARISON_JOB_TTL = timedelta(days=1)
STALE_RUNNING_JOB_AFTER = timedelta(seconds=60)
ACTIVE_STATUSES = (ComparisonJob.Status.QUEUED, ComparisonJob.Status.RUNNING)
TERMINAL_STATUSES = (
    ComparisonJob.Status.SUCCEEDED,
    ComparisonJob.Status.FAILED,
    ComparisonJob.Status.CANCELLED,
)


class ComparisonQueueFull(RuntimeError):
    pass


class ComparisonJobAccessError(PermissionError):
    pass


class ComparisonJobExpired(RuntimeError):
    pass


def _private_job_root():
    root = Path(settings.PROCESSING_JOB_ROOT).expanduser().resolve()
    media_root = Path(settings.MEDIA_ROOT).expanduser().resolve()
    if root == media_root or media_root in root.parents:
        raise RuntimeError("PROCESSING_JOB_ROOT must be outside MEDIA_ROOT.")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "posix":
        root.chmod(0o700)
    return root


def _job_directory(job_id):
    root = _private_job_root()
    candidate = root / str(job_id)
    if candidate.name != str(uuid.UUID(str(job_id))):
        raise RuntimeError("Invalid comparison job identifier.")
    return candidate


def _remove_job_directory(job_id):
    directory = _job_directory(job_id)
    if directory.is_symlink():
        directory.unlink()
        return
    resolved = directory.resolve()
    if resolved.parent != directory.parent:
        raise RuntimeError("Comparison job temporary directory escaped its private root.")
    if resolved.exists():
        if not resolved.is_dir():
            raise RuntimeError("Comparison job temporary path is not a directory.")
        shutil.rmtree(resolved)


def compression_output_path(job_id):
    directory = _job_directory(job_id)
    if directory.is_symlink():
        raise FileNotFoundError
    output = directory / "output"
    if output.is_symlink():
        raise FileNotFoundError
    resolved = output.resolve()
    if resolved.parent != directory.resolve() or not resolved.is_file():
        raise FileNotFoundError
    return resolved


def _safe_upload_name(upload):
    name = Path(upload.name.replace("\\", "/")).name[:255]
    return name or "upload.bin"


def _validate_upload(upload):
    if upload.size > MAX_COMPARISON_FILE_SIZE:
        raise ValueError("Each comparison file must be 25 MB or smaller.")
    content_type = detect_content_type(upload)
    if content_type not in SUPPORTED_CONTENT_TYPES:
        raise ValueError("Only PNG, JPEG, GIF, WEBP, and PDF files are supported.")
    return content_type


def _validate_compression_upload(upload):
    if upload.size > MAX_COMPARISON_FILE_SIZE:
        raise ValueError("The compression input must be 25 MB or smaller.")
    content_type = detect_content_type(upload)
    if content_type not in SUPPORTED_CONTENT_TYPES:
        raise ValueError("Only PNG, JPEG, GIF, WEBP, and PDF files can be compressed.")
    return content_type


def _write_private_upload(upload, destination):
    upload.seek(0)
    written = 0
    with destination.open("xb") as output:
        for chunk in upload.chunks():
            written += len(chunk)
            if written > MAX_COMPARISON_FILE_SIZE:
                raise ValueError("Each uploaded file must be 25 MB or smaller.")
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    upload.seek(0)


def _requester_fingerprint(request):
    address = request.META.get("REMOTE_ADDR", "")
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        address.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _enqueue_job(request, first, second, job_type):
    if job_type == ComparisonJob.Type.COMPRESSION:
        first_content_type = _validate_compression_upload(first)
        second_content_type = ""
    else:
        first_content_type = _validate_upload(first)
        second_content_type = _validate_upload(second)
    first.content_type = first_content_type
    if second is not None:
        second.content_type = second_content_type

    job_id = uuid.uuid4()
    token = secrets.token_urlsafe(32)
    job_directory = _job_directory(job_id)
    job_directory.mkdir(mode=0o700)
    committed = False
    try:
        _write_private_upload(first, job_directory / "first")
        if second is not None:
            _write_private_upload(second, job_directory / "second")

        owner_id = request.user.pk if request.user.is_authenticated else None
        requester_key = _requester_fingerprint(request)
        with transaction.atomic():
            try:
                ComparisonQueueControl.objects.select_for_update().get(pk=1)
            except ComparisonQueueControl.DoesNotExist as error:
                raise ProcessingEngineError(
                    "The async comparison database migration has not been applied."
                ) from error

            active = ComparisonJob.objects.filter(status__in=ACTIVE_STATUSES)
            if active.count() >= MAX_ACTIVE_COMPARISON_JOBS:
                raise ComparisonQueueFull("The comparison queue is full. Try again shortly.")
            if owner_id is not None:
                if active.filter(owner_id=owner_id).count() >= MAX_ACTIVE_JOBS_PER_OWNER:
                    raise ComparisonQueueFull(
                        "You already have the maximum number of active comparison jobs."
                    )
            elif active.filter(requester_key=requester_key).count() >= MAX_ACTIVE_JOBS_PER_CLIENT:
                raise ComparisonQueueFull(
                    "Too many active comparison jobs. Try again shortly."
                )

            job = ComparisonJob.objects.create(
                id=job_id,
                owner_id=owner_id,
                job_type=job_type,
                first_name=_safe_upload_name(first),
                second_name=_safe_upload_name(second) if second is not None else "",
                first_content_type=first_content_type,
                second_content_type=second_content_type,
                requester_key=requester_key,
                access_token_hash=hashlib.sha256(token.encode("ascii")).hexdigest(),
                expires_at=timezone.now() + COMPARISON_JOB_TTL,
            )
        committed = True
        return job, token
    finally:
        if not committed:
            _remove_job_directory(job_id)


def enqueue_comparison(request, first, second):
    return _enqueue_job(request, first, second, ComparisonJob.Type.COMPARISON)


def enqueue_compression(request, upload):
    return _enqueue_job(request, upload, None, ComparisonJob.Type.COMPRESSION)


def authorized_job(request, job_id):
    try:
        job = ComparisonJob.objects.get(pk=job_id)
    except (ComparisonJob.DoesNotExist, ValueError) as error:
        raise ComparisonJobAccessError from error

    token = request.headers.get("X-Job-Token", "")
    supplied_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if (
        not token
        or not hmac.compare_digest(supplied_hash, job.access_token_hash)
        or (
            job.owner_id is not None
            and (
                not request.user.is_authenticated
                or request.user.pk != job.owner_id
            )
        )
    ):
        raise ComparisonJobAccessError
    if job.expires_at <= timezone.now():
        raise ComparisonJobExpired
    return job


def cancel_comparison_job(job_id):
    with transaction.atomic():
        ComparisonQueueControl.objects.select_for_update().get(pk=1)
        job = ComparisonJob.objects.select_for_update().get(pk=job_id)
        if job.status == ComparisonJob.Status.QUEUED:
            job.status = ComparisonJob.Status.CANCELLED
            job.cancel_requested = True
            job.completed_at = timezone.now()
            job.save(
                update_fields=["status", "cancel_requested", "completed_at"]
            )
            cancelled_while_queued = True
        elif job.status == ComparisonJob.Status.RUNNING:
            job.cancel_requested = True
            job.save(update_fields=["cancel_requested"])
            cancelled_while_queued = False
        else:
            cancelled_while_queued = False
    if cancelled_while_queued:
        _remove_job_directory(job_id)
    return job


def claim_next_job():
    now = timezone.now()
    stale_ids = []
    job_id = None
    with transaction.atomic():
        ComparisonQueueControl.objects.select_for_update().get(pk=1)
        stale_before = now - STALE_RUNNING_JOB_AFTER
        stale_jobs = ComparisonJob.objects.filter(
            status=ComparisonJob.Status.RUNNING,
            started_at__lt=stale_before,
        )
        stale_ids = list(stale_jobs.values_list("id", flat=True))
        stale_jobs.update(
            status=ComparisonJob.Status.FAILED,
            error="The processing worker did not finish within its time limit.",
            completed_at=now,
        )
        if ComparisonJob.objects.filter(status=ComparisonJob.Status.RUNNING).count() < (
            MAX_CONCURRENT_COMPARISON_JOBS
        ):
            job = (
                ComparisonJob.objects.select_for_update()
                .filter(status=ComparisonJob.Status.QUEUED)
                .order_by("created_at")
                .first()
            )
            if job is not None:
                job.status = ComparisonJob.Status.RUNNING
                job.started_at = now
                job.save(update_fields=["status", "started_at"])
                job_id = job.id

    for stale_id in stale_ids:
        try:
            _remove_job_directory(stale_id)
        except (OSError, RuntimeError):
            logger.exception("Could not remove stale job files for %s.", stale_id)
    return job_id


def _finish_job(job_id, status, result=None, error=""):
    with transaction.atomic():
        job = ComparisonJob.objects.select_for_update().get(pk=job_id)
        if job.status in TERMINAL_STATUSES:
            return job
        if job.cancel_requested:
            job.status = ComparisonJob.Status.CANCELLED
            job.result = None
            job.error = ""
        else:
            job.status = status
            job.result = result
            job.error = error
            if (
                status == ComparisonJob.Status.SUCCEEDED
                and job.job_type == ComparisonJob.Type.COMPARISON
                and job.owner_id is not None
            ):
                report = ComparisonReport.objects.create(
                    owner_id=job.owner_id,
                    first_name=job.first_name,
                    second_name=job.second_name,
                    comparison_type=job.first_content_type,
                    result=result,
                )
                job.report_id = report.id
        job.completed_at = timezone.now()
        job.save(
            update_fields=[
                "status",
                "result",
                "error",
                "report_id",
                "completed_at",
            ]
        )
        return job


def _check_cancelled(job_id):
    return ComparisonJob.objects.filter(
        pk=job_id,
        status=ComparisonJob.Status.RUNNING,
        cancel_requested=True,
    ).exists()


def process_comparison_job(job_id):
    job = ComparisonJob.objects.get(pk=job_id)
    directory = _job_directory(job.id)
    preserve_output = False
    try:
        first_path = directory / "first"
        first_data = first_path.read_bytes()
        if job.job_type == ComparisonJob.Type.COMPRESSION:
            with cancellation_check(lambda: _check_cancelled(job_id)):
                engine_result, output_data = (
                    compress_pdf(first_data)
                    if job.first_content_type == SUPPORTED_PDF_TYPE
                    else compress_image(first_data)
                )
            if (
                engine_result.get("input_bytes") != len(first_data)
                or engine_result.get("output_bytes") != len(output_data)
                or not output_data
                or len(output_data) > MAX_COMPARISON_FILE_SIZE
            ):
                raise ProcessingEngineError(
                    "The Rust processing engine returned invalid compression output."
                )
            output_upload = SimpleUploadedFile(
                job.first_name,
                output_data,
                content_type=job.first_content_type,
            )
            _validate_signature(output_upload, job.first_content_type)
            suffix = {
                "image/png": ".png",
                "image/jpeg": ".jpg",
                "image/gif": ".gif",
                "image/webp": ".webp",
                SUPPORTED_PDF_TYPE: ".pdf",
            }[job.first_content_type]
            stem = Path(job.first_name).stem
            safe_stem = "".join(
                character if character.isalnum() or character in "._-" else "_"
                for character in stem
            ).strip("._")[:180]
            output_name = f"{safe_stem or 'file'}_compressed{suffix}"
            output_path = directory / "output"
            with output_path.open("xb") as output_file:
                output_file.write(output_data)
                output_file.flush()
                os.fsync(output_file.fileno())
            compression = {
                "input_bytes": len(first_data),
                "output_bytes": len(output_data),
                "saved_bytes": max(0, len(first_data) - len(output_data)),
                "reduced": len(output_data) < len(first_data),
                "filename": output_name,
                "content_type": job.first_content_type,
                "page_count": engine_result.get("page_count"),
            }
            completed = _finish_job(
                job_id,
                ComparisonJob.Status.SUCCEEDED,
                result=compression,
            )
            preserve_output = completed.status == ComparisonJob.Status.SUCCEEDED
        else:
            second_path = directory / "second"
            first = SimpleUploadedFile(
                job.first_name,
                first_data,
                content_type=job.first_content_type,
            )
            second = SimpleUploadedFile(
                job.second_name,
                second_path.read_bytes(),
                content_type=job.second_content_type,
            )
            with cancellation_check(lambda: _check_cancelled(job_id)):
                result = compare_uploads(first, second)
            _finish_job(job_id, ComparisonJob.Status.SUCCEEDED, result=result)
    except ProcessingCancelledError:
        _finish_job(job_id, ComparisonJob.Status.CANCELLED)
    except ValueError as error:
        _finish_job(job_id, ComparisonJob.Status.FAILED, error=str(error))
    except ProcessingEngineError as error:
        if job.job_type == ComparisonJob.Type.COMPRESSION:
            logger.error("Compression job %s failed: %s", job_id, error)
            _finish_job(job_id, ComparisonJob.Status.FAILED, error=str(error))
        else:
            logger.exception("Comparison job %s failed unexpectedly.", job_id)
            _finish_job(
                job_id,
                ComparisonJob.Status.FAILED,
                error="The comparison could not be completed.",
            )
    except Exception:
        logger.exception("Comparison job %s failed unexpectedly.", job_id)
        _finish_job(
            job_id,
            ComparisonJob.Status.FAILED,
            error="The comparison could not be completed.",
        )
    finally:
        if not preserve_output:
            try:
                _remove_job_directory(job_id)
            except OSError:
                logger.exception("Could not remove private input files for job %s.", job_id)


def cleanup_expired_jobs():
    now = timezone.now()
    queued_expired_ids = []
    with transaction.atomic():
        ComparisonQueueControl.objects.select_for_update().get(pk=1)
        expired_active = list(
            ComparisonJob.objects.select_for_update()
            .filter(status__in=ACTIVE_STATUSES, expires_at__lte=now)
            .values_list("id", "status")
        )
        queued_expired_ids = [
            job_id
            for job_id, status in expired_active
            if status == ComparisonJob.Status.QUEUED
        ]
        running_expired_ids = [
            job_id
            for job_id, status in expired_active
            if status == ComparisonJob.Status.RUNNING
        ]
        if queued_expired_ids:
            ComparisonJob.objects.filter(pk__in=queued_expired_ids).update(
                status=ComparisonJob.Status.CANCELLED,
                cancel_requested=True,
                completed_at=now,
            )
        if running_expired_ids:
            ComparisonJob.objects.filter(pk__in=running_expired_ids).update(
                cancel_requested=True,
            )

    for job_id in queued_expired_ids:
        try:
            _remove_job_directory(job_id)
        except (OSError, RuntimeError):
            logger.exception("Could not remove expired queued job files for %s.", job_id)

    expired_ids = list(
        ComparisonJob.objects.filter(
            status__in=TERMINAL_STATUSES,
            expires_at__lte=now,
        ).values_list("id", flat=True)
    )
    for job_id in expired_ids:
        try:
            _remove_job_directory(job_id)
        except (OSError, RuntimeError):
            logger.exception("Could not remove expired job files for %s.", job_id)
    ComparisonJob.objects.filter(
        status__in=TERMINAL_STATUSES,
        expires_at__lte=now,
    ).delete()

    active_ids = {
        str(job_id)
        for job_id in ComparisonJob.objects.filter(status__in=ACTIVE_STATUSES).values_list(
            "id", flat=True
        )
    }
    root = _private_job_root()
    stale_before = now.timestamp() - COMPARISON_JOB_TTL.total_seconds()
    for entry in os.scandir(root):
        if entry.name in active_ids:
            continue
        try:
            uuid.UUID(entry.name)
        except ValueError:
            continue
        candidate = root / entry.name
        if entry.is_symlink():
            candidate.unlink()
        elif entry.is_dir(follow_symlinks=False) and entry.stat(follow_symlinks=False).st_mtime < stale_before:
            _remove_job_directory(entry.name)
