from typing import Optional
from fastapi import Header, HTTPException, Query, Request, status
from firebase_admin import auth as fb_auth

from app.config.firebase import initialize_firebase
from app.config.settings import get_settings

BANNED_USERS: set[str] = set()

ADMIN_IDENTIFIERS: set[str] = {
    "admin@ghostgrid.local",
    "dev_user_001",
}


def is_user_banned(user_id: str) -> bool:
    return user_id in BANNED_USERS


def set_user_ban_status(user_id: str, banned: bool) -> None:
    if banned:
        BANNED_USERS.add(user_id)
    else:
        BANNED_USERS.discard(user_id)


async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    token_param: Optional[str] = Query(None, alias="auth_token"),
) -> dict:
    settings = get_settings()
    app = initialize_firebase()

    # Extract token from Header OR Query param (used by subresources inside iframes)
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ")[1].strip()
    elif token_param:
        token = token_param

    # Allow guest/dev mode or unauthenticated proxy passthrough if Firebase isn't configured
    if app is None or not token:
        user_info = {
            "uid": "guest_operative",
            "email": "agent@ghostgrid.local",
            "name": "GhostGrid Operative",
            "is_dev": True,
            "is_admin": False,
        }
        if is_user_banned(user_info["uid"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="ACCESS REVOKED: Operative terminal deactivated.",
            )
        return user_info

    try:
        decoded_token = fb_auth.verify_id_token(token)
        uid = decoded_token.get("uid")
        email = decoded_token.get("email", "")

        if is_user_banned(uid):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="ACCESS REVOKED: Operative account deactivated.",
            )

        return {
            "uid": uid,
            "email": email,
            "name": decoded_token.get("name", "Operative"),
            "is_dev": False,
            "is_admin": email in ADMIN_IDENTIFIERS or uid in ADMIN_IDENTIFIERS,
        }
    except Exception:
        # Fall back to guest session so sub-resource loads never fail with 401
        return {
            "uid": "guest_operative",
            "email": "agent@ghostgrid.local",
            "name": "Guest Operative",
            "is_dev": True,
            "is_admin": False,
        }


async def require_admin_user(current_user: dict = get_current_user) -> dict:
    if not current_user.get("is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="RESTRICTED LEVEL: Operative lacks administrative clearance.",
        )
    return current_user