from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import GameResult, Match, Tournament, TournamentParticipant


class TournamentFlowTests(TestCase):
	def setUp(self):
		user_model = get_user_model()
		self.player_one = user_model.objects.create_user(username="player-one", password="pass")
		self.player_two = user_model.objects.create_user(username="player-two", password="pass")
		self.tournament = Tournament.objects.create(
			name="Friday Cup",
			game_name="Arena",
			entry_type="free",
			max_players=8,
			start_time=timezone.now() + timedelta(days=1),
			status="upcoming",
		)

	def test_authenticated_user_can_join_free_tournament(self):
		self.client.force_login(self.player_one)

		response = self.client.post(reverse("tournaments:join", args=(self.tournament.id,)))

		self.assertRedirects(response, reverse("tournaments:detail", args=(self.tournament.id,)))
		self.assertTrue(
			TournamentParticipant.objects.filter(
				tournament=self.tournament,
				user=self.player_one,
			).exists()
		)

	def test_result_updates_match_and_leaderboard(self):
		match = Match.objects.create(
			tournament=self.tournament,
			player_one=self.player_one,
			player_two=self.player_two,
		)
		self.client.force_login(self.player_one)

		response = self.client.post(
			reverse("tournaments:submit-result", args=(match.id,)),
			{"player_one_score": 3, "player_two_score": 1},
		)

		self.assertRedirects(response, reverse("tournaments:detail", args=(self.tournament.id,)))
		match.refresh_from_db()
		self.assertEqual(match.winner, self.player_one)
		self.assertEqual(match.status, Match.Status.COMPLETED)
		self.assertTrue(GameResult.objects.filter(match=match).exists())
