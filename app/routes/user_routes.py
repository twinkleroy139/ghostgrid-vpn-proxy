from fastapi import APIRouter, Depends, Body
from app.middleware.auth import get_current_user
from app.services.history_service import history_service
from app.services.usage_service import usage_service
from app.services.user_service import user_service

router = APIRouter(prefix="/api/user", tags=["User & Dashboard"])


@router.get("/profile")
async def get_profile(current_user: dict = Depends(get_current_user)):
    """Returns operative profile, bookmarks, and preferences."""
    uid = current_user.get("uid", "guest_operative")
    profile = user_service.get_or_create_profile(uid)
    return {"status": "success", "profile": profile}


@router.get("/history")
async def get_history(current_user: dict = Depends(get_current_user)):
    """Returns operative's proxy browsing history."""
    uid = current_user.get("uid", "guest_operative")
    history = history_service.get_history(uid)
    return {"status": "success", "history": history}


@router.delete("/history")
async def clear_history(current_user: dict = Depends(get_current_user)):
    """Flushes operative history."""
    uid = current_user.get("uid", "guest_operative")
    history_service.clear_history(uid)
    return {"status": "success", "message": "History cleared"}


@router.post("/history/toggle")
async def toggle_history_tracking(
    enabled: bool = Body(..., embed=True),
    current_user: dict = Depends(get_current_user),
):
    """Enables or disables history logging."""
    uid = current_user.get("uid", "guest_operative")
    history_service.set_tracking(uid, enabled)
    user_service.update_preferences(uid, track_history=enabled)
    return {"status": "success", "track_history": enabled}


@router.get("/bookmarks")
async def get_bookmarks(current_user: dict = Depends(get_current_user)):
    """Returns list of operative saved bookmarks."""
    uid = current_user.get("uid", "guest_operative")
    profile = user_service.get_or_create_profile(uid)
    return {"status": "success", "bookmarks": profile["bookmarks"]}


@router.post("/bookmarks")
async def add_bookmark(
    title: str = Body(..., embed=True),
    url: str = Body(..., embed=True),
    current_user: dict = Depends(get_current_user),
):
    """Adds a bookmark."""
    uid = current_user.get("uid", "guest_operative")
    bookmarks = user_service.add_bookmark(uid, title, url)
    return {"status": "success", "bookmarks": bookmarks}


@router.delete("/bookmarks")
async def delete_bookmark(
    url: str = Body(..., embed=True),
    current_user: dict = Depends(get_current_user),
):
    """Deletes a bookmark."""
    uid = current_user.get("uid", "guest_operative")
    bookmarks = user_service.remove_bookmark(uid, url)
    return {"status": "success", "bookmarks": bookmarks}


@router.get("/usage")
async def get_usage(current_user: dict = Depends(get_current_user)):
    """Returns operative bandwidth and request count telemetry."""
    uid = current_user.get("uid", "guest_operative")
    usage = usage_service.get_user_usage(uid)
    return {"status": "success", "usage": usage}