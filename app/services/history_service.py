import time
from typing import Dict, List, Optional
from urllib.parse import urlparse

from app.config.firebase import get_firestore_client


class HistoryService:
    """
    Manages operative browsing history with privacy controls.
    Supports in-memory storage with Firestore sync when enabled.
    """

    def __init__(self):
        # In-memory storage: { user_id: [ {"url": ..., "domain": ..., "timestamp": ...} ] }
        self._history_store: Dict[str, List[dict]] = {}
        # History recording toggle per user: { user_id: bool }
        self._tracking_enabled: Dict[str, bool] = {}

    def is_tracking_enabled(self, user_id: str) -> bool:
        """Defaults to True unless operative disabled history tracking."""
        return self._tracking_enabled.get(user_id, True)

    def set_tracking(self, user_id: str, enabled: bool) -> None:
        """Toggles history recording for a user."""
        self._tracking_enabled[user_id] = enabled

    def add_entry(self, user_id: str, target_url: str, title: str = "") -> None:
        """Adds a new URL entry to operative history if tracking is enabled."""
        if not self.is_tracking_enabled(user_id):
            return

        parsed = urlparse(target_url)
        entry = {
            "url": target_url,
            "domain": parsed.hostname or target_url,
            "title": title or parsed.hostname or target_url,
            "timestamp": int(time.time()),
        }

        if user_id not in self._history_store:
            self._history_store[user_id] = []

        # Keep history capped at 100 recent entries
        self._history_store[user_id].insert(0, entry)
        if len(self._history_store[user_id]) > 100:
            self._history_store[user_id].pop()

        # Sync to Firestore if active
        db = get_firestore_client()
        if db:
            try:
                db.collection("users").document(user_id).collection("history").add(entry)
            except Exception:
                pass

    def get_history(self, user_id: str) -> List[dict]:
        """Returns the list of recent history items for a user."""
        return self._history_store.get(user_id, [])

    def clear_history(self, user_id: str) -> None:
        """Flushes all stored history for a user."""
        if user_id in self._history_store:
            self._history_store[user_id] = []


history_service = HistoryService()