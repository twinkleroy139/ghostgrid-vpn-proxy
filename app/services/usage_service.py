from typing import Dict


class UsageService:
    """Tracks operative usage metrics (total bandwidth transferred and request count)."""

    def __init__(self):
        # { user_id: { "requests": int, "bytes": int } }
        self._metrics: Dict[str, Dict[str, int]] = {}

    def record_usage(self, user_id: str, bytes_count: int) -> None:
        """Increments request counter and data volume for a user."""
        if user_id not in self._metrics:
            self._metrics[user_id] = {"requests": 0, "bytes": 0}

        self._metrics[user_id]["requests"] += 1
        self._metrics[user_id]["bytes"] += bytes_count

    def get_user_usage(self, user_id: str) -> dict:
        """Returns usage stats for a specific operative."""
        stats = self._metrics.get(user_id, {"requests": 0, "bytes": 0})
        mb_transferred = round(stats["bytes"] / (1024 * 1024), 2)
        return {
            "requests": stats["requests"],
            "bytes": stats["bytes"],
            "megabytes": mb_transferred,
        }


usage_service = UsageService()