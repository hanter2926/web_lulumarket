from django.urls import path
from . import views

app_name = 'videos'

urlpatterns = [
    path('upload/', views.video_upload, name='upload'),
    path('my/', views.my_videos, name='my_videos'),
    path('<int:pk>/', views.video_detail, name='detail'),
]
