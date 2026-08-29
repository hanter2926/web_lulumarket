import subprocess
from pathlib import Path
from django.conf import settings


def extract_audio(video_path: str, output_path: str) -> bool:
    """Extracts audio from video using ffmpeg.

    Returns True on success, False otherwise.
    """
    ffmpeg = getattr(settings, 'FFMPEG_PATH', 'ffmpeg')
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        '-y',
        '-i', str(video_path),
        '-vn',
        '-acodec', 'pcm_s16le',
        '-ar', '44100',
        '-ac', '2',
        str(output_path)
    ]
    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f'ffmpeg audio extraction failed: {e}')
