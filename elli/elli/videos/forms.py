from django import forms
from django.conf import settings
from .models import Video
from pathlib import Path


ALLOWED_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}


class VideoUploadForm(forms.ModelForm):
    class Meta:
        model = Video
        fields = ('title', 'original_video', 'voice_mode', 'selected_voice', 'custom_voice_consent')

    def clean_original_video(self):
        f = self.cleaned_data.get('original_video')
        if not f:
            raise forms.ValidationError('No file uploaded')

        ext = Path(f.name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise forms.ValidationError('Unsupported file extension.')

        max_mb = int(getattr(settings, 'MAX_UPLOAD_SIZE_MB', 500))
        if f.size > max_mb * 1024 * 1024:
            raise forms.ValidationError(f'File too large. Max size is {max_mb} MB')

        return f
