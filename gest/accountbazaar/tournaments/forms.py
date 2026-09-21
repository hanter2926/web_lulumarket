from django import forms

from .models import GameResult, Tournament


class TournamentForm(forms.ModelForm):
    class Meta:
        model = Tournament
        fields = ("name", "game_name", "entry_type", "entry_fee", "prize_pool", "max_players", "start_time")
        widgets = {"start_time": forms.DateTimeInput(attrs={"type": "datetime-local"})}


class GameResultForm(forms.ModelForm):
    class Meta:
        model = GameResult
        fields = ("player_one_score", "player_two_score")
