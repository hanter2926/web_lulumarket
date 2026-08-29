import os
from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from pathlib import Path

from .models import Video
from .services import (
    audio as audio_svc,
    transcription as trans_svc,
    translation as translat_svc,
    tts as tts_svc,
    synchronization as sync_svc,
    subtitles as subs_svc,
    video as video_svc,
)


@shared_task(bind=True)
def process_video(self, video_id: int):
    video = Video.objects.get(pk=video_id)
    try:
        video.status = Video.STATUS_EXTRACTING
        video.progress = 5
        video.save()

        # Ensure media paths and extract audio
        orig_path = Path(video.original_video.path)
        audio_out_rel = video.original_audio.field.upload_to(video, 'extracted.wav')
        audio_out = Path(settings.MEDIA_ROOT) / audio_out_rel
        audio_out.parent.mkdir(parents=True, exist_ok=True)

        audio_svc.extract_audio(orig_path, audio_out)

        # attach original_audio file
        with open(audio_out, 'rb') as f:
            video.original_audio.save(audio_out.name, ContentFile(f.read()), save=False)

        video.status = Video.STATUS_TRANSCRIBING
        video.progress = 20
        video.save()

        segments = trans_svc.transcribe_with_whisper(str(audio_out))

        video.english_transcript = '\n'.join([s.get('text', '') for s in segments])
        video.progress = 40
        video.status = Video.STATUS_TRANSLATING
        video.save()

        segments_trans = translat_svc.translate_segments_to_hindi(segments)
        video.hindi_transcript = '\n'.join([s.get('text_hindi', '') for s in segments_trans])
        video.progress = 60
        video.status = Video.STATUS_GENERATING_VOICE
        video.save()

        # Synthesize TTS for the full translated transcript
        gen_audio_rel = video.generated_hindi_audio.field.upload_to(video, 'gen.wav')
        gen_audio_path = Path(settings.MEDIA_ROOT) / gen_audio_rel
        gen_audio_path.parent.mkdir(parents=True, exist_ok=True)
        tts_svc.synthesize_hindi_text(video.hindi_transcript or '', str(gen_audio_path), voice=video.selected_voice or None)

        with open(gen_audio_path, 'rb') as f:
            video.generated_hindi_audio.save(gen_audio_path.name, ContentFile(f.read()), save=False)

        video.progress = 75
        video.status = Video.STATUS_GENERATING_SUBTITLES
        video.save()

        srt_text = subs_svc.segments_to_srt(segments_trans)
        srt_rel = video.subtitle_file.field.upload_to(video, 'subs.srt')
        srt_path = Path(settings.MEDIA_ROOT) / srt_rel
        srt_path.parent.mkdir(parents=True, exist_ok=True)
        srt_path.write_text(srt_text, encoding='utf-8')

        with open(srt_path, 'rb') as f:
            video.subtitle_file.save(srt_path.name, ContentFile(f.read()), save=False)

        video.progress = 85
        video.status = Video.STATUS_RENDERING
        video.save()

        processed_rel = video.processed_video.field.upload_to(video, 'processed.mp4')
        processed_out = Path(settings.MEDIA_ROOT) / processed_rel
        processed_out.parent.mkdir(parents=True, exist_ok=True)

        # Burn subtitles; keep original audio or replace with generated Hindi audio depending on requirements
        # As per request, replace audio in processed version with generated Hindi audio
        # We'll first create a temporary muxed file combining original video streams with new audio
        # Implemented inside video_svc.merge_video_with_audio
        ok = video_svc.merge_video_with_audio(str(orig_path), str(gen_audio_path), str(srt_path), str(processed_out))
        if not ok:
            raise RuntimeError('Rendering processed video failed')

        with open(processed_out, 'rb') as f:
            video.processed_video.save(processed_out.name, ContentFile(f.read()), save=False)

        video.progress = 100
        video.status = Video.STATUS_COMPLETED
        video.save()

    except Exception as exc:
        video.status = Video.STATUS_FAILED
        video.error_message = str(exc)
        video.save()
        raise
