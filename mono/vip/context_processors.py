from .models import SiteSettings


def site_settings(request):
    site_setting = SiteSettings.get_active()
    return {
        'site_setting': site_setting,
    }
