from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import GameResultForm, TournamentForm
from .models import GameResult, Match, Tournament, TournamentParticipant


def tournament_list(request):
	query = request.GET.get("q", "").strip()
	tournaments = Tournament.objects.prefetch_related("participants").order_by("start_time")
	if query:
		tournaments = tournaments.filter(Q(name__icontains=query) | Q(game_name__icontains=query))
	return render(request, "tournaments/list.html", {"tournaments": tournaments, "query": query})


def tournament_detail(request, tournament_id):
	tournament = get_object_or_404(
		Tournament.objects.prefetch_related("participants__user", "matches__player_one", "matches__player_two"),
		pk=tournament_id,
	)
	leaderboard = []
	for participant in tournament.participants.all():
		participant.wins = Match.objects.filter(
			tournament=tournament,
			winner=participant.user,
			status=Match.Status.COMPLETED,
		).count()
		leaderboard.append(participant)
	leaderboard.sort(key=lambda entry: (-entry.wins, entry.joined_at))
	return render(
		request,
		"tournaments/detail.html",
		{"tournament": tournament, "leaderboard": leaderboard, "result_form": GameResultForm()},
	)


@login_required
def create_tournament(request):
	form = TournamentForm(request.POST or None)
	if request.method == "POST" and form.is_valid():
		tournament = form.save(commit=False)
		tournament.status = "upcoming"
		tournament.save()
		return redirect("tournaments:detail", tournament_id=tournament.id)
	return render(request, "tournaments/create.html", {"form": form})


@login_required
@require_POST
def join_tournament(request, tournament_id):
	tournament = get_object_or_404(Tournament, pk=tournament_id)
	if tournament.participants.count() < tournament.max_players:
		TournamentParticipant.objects.get_or_create(tournament=tournament, user=request.user)
	return redirect("tournaments:detail", tournament_id=tournament.id)


@login_required
@require_POST
def submit_result(request, match_id):
	match = get_object_or_404(Match, pk=match_id)
	if request.user.id not in (match.player_one_id, match.player_two_id):
		return redirect("tournaments:detail", tournament_id=match.tournament_id)
	form = GameResultForm(request.POST)
	if form.is_valid() and form.cleaned_data["player_one_score"] != form.cleaned_data["player_two_score"]:
		with transaction.atomic():
			result, _ = GameResult.objects.update_or_create(
				match=match,
				defaults={
					"player_one_score": form.cleaned_data["player_one_score"],
					"player_two_score": form.cleaned_data["player_two_score"],
					"submitted_by": request.user,
					"verified": False,
				},
			)
			match.winner = match.player_one if result.player_one_score > result.player_two_score else match.player_two
			match.status = Match.Status.COMPLETED
			match.save(update_fields=("winner", "status"))
	return redirect("tournaments:detail", tournament_id=match.tournament_id)
