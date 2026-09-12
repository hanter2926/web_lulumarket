from django.test import Client
from django.urls import reverse
from django.urls import NoReverseMatch
from accounts.models import CustomUser, UserProfile

c = Client()
results = []

def add(name, status, ok, info=""):
    results.append((name, status, ok, info))

# Homepage
try:
    home_url = reverse('home')
    r = c.get(home_url)
    content = r.content.decode('utf-8', errors='replace')
    err = any(x in content for x in ['NoReverseMatch', 'TemplateSyntaxError', 'Traceback'])
    add('home', r.status_code, (r.status_code==200 and not err), 'TemplateError' if err else '')
except Exception as e:
    add('home', 'EXC', False, repr(e))

# Navbar links
for label, rev in [('dashboard', 'accounts:dashboard_page'), ('settings', 'accounts:account_settings'), ('login', 'accounts:email_login')]:
    try:
        u = reverse(rev)
        r = c.get(u)
        content = r.content.decode('utf-8', errors='replace')
        err = any(x in content for x in ['NoReverseMatch', 'TemplateSyntaxError', 'Traceback'])
        add(rev, r.status_code, (r.status_code==200 and not err), '')
    except Exception as e:
        add(rev, 'EXC', False, repr(e))

# Create a verified test user and attempt login
try:
    user = CustomUser.objects.create_user(email='testuser@example.com', username='testuser', password='pass123')
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.is_phone_verified = True
    profile.save(update_fields=['is_phone_verified', 'updated_at'])

    r = c.post(reverse('accounts:email_login'), {'email': 'testuser@example.com', 'password': 'pass123'})
    add('login_post', r.status_code, r.status_code in (302, 301), r.url if r.status_code in (301,302) else '')
    # After login, access dashboard
    r2 = c.get(reverse('accounts:dashboard_page'))
    add('dashboard_after_login', r2.status_code, r2.status_code==200, '')
except Exception as e:
    add('login_flow', 'EXC', False, repr(e))

# Protected pages as anonymous
anon = Client()
protected = ['checkout', 'checkout_address', 'checkout_payment', 'payment_page']
for pagename in protected:
    try:
        if pagename == 'payment_page':
            try:
                url = reverse('payment_page', args=[1])
            except Exception as e:
                add(pagename, 'EXC', False, repr(e))
                continue
        else:
            url = reverse(pagename)
    except Exception as e:
        add(pagename, 'EXC', False, repr(e))
        continue
    r = anon.get(url)
    loc = r.get('Location', '')
    try:
        login_url = reverse('accounts:email_login')
    except Exception:
        login_url = '/accounts/login/'
    redirected = (r.status_code in (301,302) and login_url in (loc or ''))
    add(pagename, r.status_code, redirected, loc)

# Settings page while logged in
try:
    r = c.get(reverse('accounts:account_settings'))
    content = r.content.decode('utf-8', errors='replace')
    err = any(x in content for x in ['NoReverseMatch', 'TemplateSyntaxError', 'Traceback'])
    add('settings_page', r.status_code, (r.status_code==200 and not err), '')
except Exception as e:
    add('settings_page', 'EXC', False, repr(e))

# Print results
for name, status, ok, info in results:
    print(f"{name}: status={status} ok={ok} info={info}")
print('done')
