import os
from uuid import uuid4
from pathlib import Path
from django.conf import settings
from django.db import models


def _secure_filename(filename: str) -> str:
    ext = Path(filename).suffix
    return f"{uuid4().hex}{ext}"


def original_video_upload_to(instance, filename):
    filename = _secure_filename(filename)
    return os.path.join('uploads', str(instance.user.id), filename)


def extracted_audio_upload_to(instance, filename):
    filename = _secure_filename(filename)
    return os.path.join('audio', str(instance.user.id), filename)


def generated_audio_upload_to(instance, filename):
    filename = _secure_filename(filename)
    return os.path.join('audio', 'generated', str(instance.user.id), filename)


def subtitle_upload_to(instance, filename):
    filename = _secure_filename(filename)
    return os.path.join('subtitles', str(instance.user.id), filename)


def processed_video_upload_to(instance, filename):
    filename = _secure_filename(filename)
    return os.path.join('processed', str(instance.user.id), filename)


class Video(models.Model):
    STATUS_UPLOADED = 'uploaded'
    STATUS_QUEUED = 'queued'
    STATUS_EXTRACTING = 'extracting_audio'
    STATUS_TRANSCRIBING = 'transcribing'
    STATUS_TRANSLATING = 'translating'
    STATUS_GENERATING_VOICE = 'generating_voice'
    STATUS_GENERATING_SUBTITLES = 'generating_subtitles'
    STATUS_RENDERING = 'rendering'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_UPLOADED, 'Uploaded'),
        (STATUS_QUEUED, 'Queued'),
        (STATUS_EXTRACTING, 'Extracting Audio'),
        (STATUS_TRANSCRIBING, 'Transcribing'),
        (STATUS_TRANSLATING, 'Translating'),
        (STATUS_GENERATING_VOICE, 'Generating Voice'),
        (STATUS_GENERATING_SUBTITLES, 'Generating Subtitles'),
        (STATUS_RENDERING, 'Rendering'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='videos'
    )

    title = models.CharField(max_length=255)

    original_video = models.FileField(upload_to=original_video_upload_to)

    original_audio = models.FileField(
        upload_to=extracted_audio_upload_to,
        null=True,
        blank=True
    )

    english_transcript = models.TextField(null=True, blank=True)

    hindi_transcript = models.TextField(null=True, blank=True)

    generated_hindi_audio = models.FileField(
        upload_to=generated_audio_upload_to,
        null=True,
        blank=True
    )

    subtitle_file = models.FileField(
        upload_to=subtitle_upload_to,
        null=True,
        blank=True
    )

    processed_video = models.FileField(
        upload_to=processed_video_upload_to,
        null=True,
        blank=True
    )

    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_UPLOADED
    )

    progress = models.PositiveSmallIntegerField(default=0)

    error_message = models.TextField(null=True, blank=True)

    # Optional fields for voice control and consent
    voice_mode = models.CharField(max_length=32, null=True, blank=True)
    selected_voice = models.CharField(max_length=128, null=True, blank=True)
    custom_voice_consent = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.id} - {self.title} ({self.user})"
