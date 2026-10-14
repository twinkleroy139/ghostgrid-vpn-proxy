from fastapi import APIRouter, Depends, Body, HTTPException, status
from app.middleware.auth import get_current_user, require_admin_user, set_user_ban_status, BANNED_USERS
from app.services.usage_service import usage_service
from app.services.history_service import history_service
from app.security.blocklist import DEFAULT_BLOCKED_DOMAINS

router = APIRouter(prefix="/api/admin", tags=["Administration & Moderation"])


@router.get("/overview")
async def get_system_overview(current_user: dict = Depends(get_current_user)):
    """System diagnostic metrics, active bans, and domain rules."""
    await require_admin_user(current_user)

    total_requests = sum(v["requests"] for v in usage_service._metrics.values())
    total_bytes = sum(v["bytes"] for v in usage_service._metrics.values())
    total_mb = round(total_bytes / (1024 * 1024), 2)

    return {
        "status": "online",
        "system": "GhostGrid Central Command",
        "banned_count": len(BANNED_USERS),
        "banned_users": list(BANNED_USERS),
        "total_requests": total_requests,
        "total_bandwidth_mb": total_mb,
        "blocked_domains_count": len(DEFAULT_BLOCKED_DOMAINS),
    }


@router.post("/ban")
async def ban_operative(
    user_id: str = Body(..., embed=True),
    current_user: dict = Depends(get_current_user),
):
    """Bans an operative ID from all proxy tunneling."""
    await require_admin_user(current_user)
    if user_id == current_user.get("uid"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Self-lockout prevented: You cannot ban your own administrative identity.",
        )
    set_user_ban_status(user_id, banned=True)
    return {"status": "success", "message": f"Operative {user_id} added to revocation list."}


@router.post("/unban")
async def unban_operative(
    user_id: str = Body(..., embed=True),
    current_user: dict = Depends(get_current_user),
):
    """Restores access for a banned operative."""
    await require_admin_user(current_user)
    set_user_ban_status(user_id, banned=False)
    return {"status": "success", "message": f"Operative {user_id} reinstated."}