from django import template

register = template.Library()


@register.filter
def discount_percent(price, compare_price):
    """Return discount percentage as integer if compare_price > price and compare_price>0.

    Usage in templates: {{ product.price|discount_percent:product.compare_price }}
    """
    try:
        if compare_price and float(compare_price) > 0 and float(compare_price) > float(price):
            discount = ((float(compare_price) - float(price)) / float(compare_price)) * 100.0
            # Round to nearest integer for badge display
            return int(round(discount))
    except (TypeError, ValueError):
        return ''
    return ''
