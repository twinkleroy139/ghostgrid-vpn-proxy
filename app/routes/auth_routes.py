from fastapi import APIRouter, Depends
from app.middleware.auth import get_current_user

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.get("/me")
async def get_my_profile(current_user: dict = Depends(get_current_user)):
    """Returns the currently authenticated user's session data."""
    return {
        "status": "authenticated",
        "user": current_user,
    }


@router.get("/health")
async def auth_health():
    """Simple heartbeat for the auth system."""
    return {"status": "online", "system": "GhostGrid Auth Subsystem"}