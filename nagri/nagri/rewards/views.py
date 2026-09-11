from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .utils import claim_daily_reward, format_reward_value


@login_required(login_url="login_page")
@require_POST
def claim_mystery_reward(request):
    claim, created, message = claim_daily_reward(request.user)

    if not claim:
        return JsonResponse({"success": False, "message": message}, status=400)

    reward = claim.reward_type
    return JsonResponse(
        {
            "success": True,
            "created": created,
            "message": message,
            "claim": {
                "reward_code": claim.reward_code,
                "reward_label": format_reward_value(claim),
                "reward_name": reward.name,
                "reward_kind": reward.reward_kind,
                "claimed_date": claim.claimed_date.isoformat(),
                "expires_at": claim.expires_at.isoformat(),
                "is_used": claim.is_used,
                "is_active": claim.is_active,
                "state": claim.display_state,
                "description": reward.description,
            },
        }
    )