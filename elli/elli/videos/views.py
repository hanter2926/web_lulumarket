from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .forms import VideoUploadForm
from .models import Video


@login_required
def video_upload(request):
    if request.method == 'POST':
        form = VideoUploadForm(request.POST, request.FILES)
        if form.is_valid():
            video = form.save(commit=False)
            video.user = request.user
            video.status = Video.STATUS_UPLOADED
            video.save()
            messages.success(request, 'Video uploaded and queued for processing.')
            return redirect('videos:my_videos')
    else:
        form = VideoUploadForm()

    return render(request, 'videos/upload.html', {'form': form})


@login_required
def my_videos(request):
    qs = Video.objects.filter(user=request.user)
    return render(request, 'videos/my_videos.html', {'videos': qs})


@login_required
def video_detail(request, pk):
    video = get_object_or_404(Video, pk=pk, user=request.user)
    return render(request, 'videos/detail.html', {'video': video})
