from django.db import models


class Tournament(models.Model):

    name = models.CharField(max_length=200)

    game_name = models.CharField(max_length=100)

    entry_type = models.CharField(
        max_length=20,
        choices=[
            ("free", "Free"),
            ("paid", "Paid"),
        ]
    )

    entry_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    prize_pool = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    max_players = models.PositiveIntegerField()

    start_time = models.DateTimeField()

    status = models.CharField(
        max_length=30,
        default="draft"
    )
