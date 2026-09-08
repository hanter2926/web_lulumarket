from .models import Category


def nav_categories(request):
    """Provide grouped categories and their subcategories for the site navbar.

    Groups are determined by simple keyword matching on category names so we
    can show relevant categories under Fashion, Home & Kitchen, and Mobiles.
    This is safe and non-destructive — if no categories match a group the
    dropdown remains empty.
    """
    categories = Category.objects.prefetch_related('subcategories').all().order_by('name')

    def matches(cat_name, keywords):
        name = (cat_name or '').lower()
        return any(k.lower() in name for k in keywords)

    fashion_keys = ['men', 'women', 'fashion', 'apparel', 'clothing']
    home_keys = ['home', 'kitchen', 'home & kitchen', 'homeware']
    mobiles_keys = ['mobile', 'phone', 'tablet', 'electronics', 'mobiles', 'tablets']

    fashion = []
    home = []
    mobiles = []

    for cat in categories:
        item = {
            'id': cat.id,
            'name': cat.name,
            'slug': getattr(cat, 'slug', ''),
            'subcategories': list(cat.subcategories.all().values('id', 'name', 'slug'))
        }
        if matches(cat.name, fashion_keys):
            fashion.append(item)
        if matches(cat.name, home_keys):
            home.append(item)
        if matches(cat.name, mobiles_keys):
            mobiles.append(item)

    # Also return all categories for generic usage (keeps backward compatibility)
    all_cats = list(categories.values('id', 'name', 'slug'))

    return {
        'nav_fashion_categories': fashion,
        'nav_home_categories': home,
        'nav_mobiles_categories': mobiles,
        'nav_all_categories': all_cats,
    }
