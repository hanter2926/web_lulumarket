from django.contrib import admin
from .models import Video


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'user', 'status', 'progress', 'created_at')
    list_filter = ('status', 'created_at', 'user')
    search_fields = ('title', 'english_transcript', 'hindi_transcript')
    readonly_fields = ('created_at', 'updated_at')
