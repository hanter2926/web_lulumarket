from django.conf import settings
from django.db import models
from django.utils import timezone


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


class TournamentParticipant(models.Model):
    class Status(models.TextChoices):
        REGISTERED = "registered", "Registered"
        ELIMINATED = "eliminated", "Eliminated"
        WINNER = "winner", "Winner"

    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name="participants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tournament_entries")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REGISTERED)
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("tournament", "user"), name="unique_tournament_participant"),
        ]


class Match(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        LIVE = "live", "Live"
        COMPLETED = "completed", "Completed"

    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name="matches")
    round_number = models.PositiveIntegerField(default=1)
    player_one = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="matches_as_player_one")
    player_two = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="matches_as_player_two")
    winner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="won_matches")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class GameResult(models.Model):
    match = models.OneToOneField(Match, on_delete=models.CASCADE, related_name="result")
    player_one_score = models.PositiveIntegerField(default=0)
    player_two_score = models.PositiveIntegerField(default=0)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="submitted_results")
    verified = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(auto_now_add=True)
