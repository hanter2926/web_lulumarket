from .models import SiteSettings


def site_settings(request):
    site_setting = SiteSettings.get_active()
    # If the registration flow set a session flag, surface the active popup once and clear the flag
    account_popup = None
    try:
        if request.session.pop('show_account_popup', False):
            from .models import AccountPopup
            account_popup = AccountPopup.objects.filter(is_active=True).first()
    except Exception:
        account_popup = None

    return {
        'site_setting': site_setting,
        'account_popup': account_popup,
    }
