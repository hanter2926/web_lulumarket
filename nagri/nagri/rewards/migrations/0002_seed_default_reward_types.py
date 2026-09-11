from django.db import migrations


def create_default_reward_types(apps, schema_editor):
    MysteryRewardType = apps.get_model("rewards", "MysteryRewardType")

    defaults = [
        {
            "name": "₹20 OFF Coupon",
            "reward_kind": "amount_off",
            "amount_off": 20,
            "percent_off": 0,
            "description": "Instant ₹20 discount on your order.",
            "weight": 5,
            "is_active": True,
            "display_order": 1,
        },
        {
            "name": "₹50 OFF Coupon",
            "reward_kind": "amount_off",
            "amount_off": 50,
            "percent_off": 0,
            "description": "Instant ₹50 discount on your order.",
            "weight": 3,
            "is_active": True,
            "display_order": 2,
        },
        {
            "name": "5% OFF",
            "reward_kind": "percent_off",
            "amount_off": 0,
            "percent_off": 5,
            "description": "Get 5% off your order total.",
            "weight": 4,
            "is_active": True,
            "display_order": 3,
        },
        {
            "name": "10% OFF",
            "reward_kind": "percent_off",
            "amount_off": 0,
            "percent_off": 10,
            "description": "Get 10% off your order total.",
            "weight": 2,
            "is_active": True,
            "display_order": 4,
        },
        {
            "name": "Free Delivery",
            "reward_kind": "free_delivery",
            "amount_off": 0,
            "percent_off": 0,
            "description": "Enjoy free delivery on your order.",
            "weight": 3,
            "is_active": True,
            "display_order": 5,
        },
    ]

    for item in defaults:
        MysteryRewardType.objects.update_or_create(
            name=item["name"],
            defaults=item,
        )


def remove_default_reward_types(apps, schema_editor):
    MysteryRewardType = apps.get_model("rewards", "MysteryRewardType")
    MysteryRewardType.objects.filter(
        name__in=[
            "₹20 OFF Coupon",
            "₹50 OFF Coupon",
            "5% OFF",
            "10% OFF",
            "Free Delivery",
        ]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("rewards", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_default_reward_types, reverse_code=remove_default_reward_types),
    ]