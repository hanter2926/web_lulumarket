import subprocess
from pathlib import Path
from django.conf import settings


def burn_subtitles(original_video_path: str, srt_path: str, output_path: str) -> bool:
    """Burn subtitles into the video using ffmpeg. Keeps original audio unchanged."""
    ffmpeg = settings.FFMPEG_PATH or 'ffmpeg'
    cmd = [
        ffmpeg,
        '-y',
        '-i', str(original_video_path),
        '-vf', f"subtitles={srt_path}",
        '-c:a', 'copy',
        str(output_path)
    ]
    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def merge_video_with_audio(original_video_path: str, new_audio_path: str, srt_path: str, output_path: str) -> bool:
    """Replace the audio of the original video with new audio and burn subtitles.

    Steps:
    1. Use ffmpeg to take video stream from original and audio from new_audio_path.
    2. Burn subtitles using subtitles filter.
    """
    ffmpeg = settings.FFMPEG_PATH or 'ffmpeg'
    cmd = [
        ffmpeg,
        '-y',
        '-i', str(original_video_path),
        '-i', str(new_audio_path),
        '-map', '0:v:0',
        '-map', '1:a:0',
        '-c:v', 'libx264',
        '-crf', '23',
        '-preset', 'veryfast',
        '-c:a', 'aac',
        '-b:a', '192k',
        '-vf', f"subtitles={srt_path}",
        str(output_path)
    ]
    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f'ffmpeg merge failed: {e}')
