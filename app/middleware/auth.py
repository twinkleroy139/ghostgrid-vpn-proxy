from typing import Optional
from fastapi import Header, HTTPException, Request, status
from firebase_admin import auth as fb_auth

from app.config.firebase import initialize_firebase
from app.config.settings import get_settings

# In-memory ban registry: { "user_id": True }
BANNED_USERS: set[str] = set()

# Admin IDs or emails
ADMIN_IDENTIFIERS: set[str] = {
    "admin@ghostgrid.local",
    "dev_user_001",
}


def is_user_banned(user_id: str) -> bool:
    """Checks if operative ID is present in the ban registry."""
    return user_id in BANNED_USERS


def set_user_ban_status(user_id: str, banned: bool) -> None:
    """Bans or unbans an operative."""
    if banned:
        BANNED_USERS.add(user_id)
    else:
        BANNED_USERS.discard(user_id)


async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
) -> dict:
    """
    Validates Firebase ID token and checks against the ban registry.
    """
    settings = get_settings()
    app = initialize_firebase()

    # 1. Dev fallback mode
    if app is None or settings.ENVIRONMENT == "development" and not authorization:
        user_info = {
            "uid": "dev_user_001",
            "email": "agent@ghostgrid.local",
            "name": "GhostGrid Operative",
            "is_dev": True,
            "is_admin": True,
        }
        if is_user_banned(user_info["uid"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="ACCESS REVOKED: This operative terminal has been deactivated by administration.",
            )
        return user_info

    # 2. Production Firebase verification
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header. Expected 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split("Bearer ")[1].strip()

    try:
        decoded_token = fb_auth.verify_id_token(token)
        uid = decoded_token.get("uid")
        email = decoded_token.get("email", "")

        if is_user_banned(uid):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="ACCESS REVOKED: This operative account has been deactivated.",
            )

        return {
            "uid": uid,
            "email": email,
            "name": decoded_token.get("name", "Operative"),
            "is_dev": False,
            "is_admin": email in ADMIN_IDENTIFIERS or uid in ADMIN_IDENTIFIERS,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired credentials: {str(exc)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_admin_user(
    current_user: dict = get_current_user,
) -> dict:
    """Dependency that ensures the requesting operative holds administrative privileges."""
    # When used as a FastAPI dependency, get_current_user will be resolved first
    if not current_user.get("is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="RESTRICTED LEVEL: Operative lacks administrative clearance.",
        )
    return current_user