from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0005_order_cancellation_comment_order_cancellation_reason_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="inventory_reserved",
            field=models.BooleanField(default=False),
        ),
    ]
