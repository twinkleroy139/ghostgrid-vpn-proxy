from typing import Dict, List, Optional
from app.config.firebase import get_firestore_client


class UserService:
    """Manages operative preferences (theme, privacy toggles) and bookmarks."""

    def __init__(self):
        # Default in-memory profile: { user_id: { "theme": "cyberpunk", "bookmarks": [...] } }
        self._profiles: Dict[str, dict] = {}

    def get_or_create_profile(self, user_id: str) -> dict:
        """Retrieves user profile or initializes default operative preferences."""
        if user_id not in self._profiles:
            self._profiles[user_id] = {
                "user_id": user_id,
                "theme": "cyberpunk",
                "track_history": True,
                "bookmarks": [
                    {"title": "Wikipedia", "url": "https://en.wikipedia.org"},
                    {"title": "DuckDuckGo", "url": "https://duckduckgo.com"},
                    {"title": "Hacker News", "url": "https://news.ycombinator.com"},
                ],
            }
        return self._profiles[user_id]

    def add_bookmark(self, user_id: str, title: str, url: str) -> List[dict]:
        """Adds a new URL to the user's bookmarks list."""
        profile = self.get_or_create_profile(user_id)
        # Avoid duplicate URLs
        if not any(b["url"] == url for b in profile["bookmarks"]):
            profile["bookmarks"].append({"title": title or url, "url": url})
        return profile["bookmarks"]

    def remove_bookmark(self, user_id: str, url: str) -> List[dict]:
        """Removes a URL from bookmarks."""
        profile = self.get_or_create_profile(user_id)
        profile["bookmarks"] = [b for b in profile["bookmarks"] if b["url"] != url]
        return profile["bookmarks"]

    def update_preferences(self, user_id: str, theme: Optional[str] = None, track_history: Optional[bool] = None) -> dict:
        """Updates UI themes or history tracking flags."""
        profile = self.get_or_create_profile(user_id)
        if theme is not None:
            profile["theme"] = theme
        if track_history is not None:
            profile["track_history"] = track_history
        return profile


user_service = UserService()