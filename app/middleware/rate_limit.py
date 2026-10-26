import time
from collections import defaultdict
from typing import Dict, List
from fastapi import HTTPException, Request, status

# Sliding-window rate limit tracker: { key: [timestamp1, timestamp2, ...] }
_rate_limit_records: Dict[str, List[float]] = defaultdict(list)

# Limits: Max 1200 requests per minute per client IP to support complex modern SPAs
MAX_REQUESTS_PER_WINDOW = 1200
WINDOW_SECONDS = 60.0


def check_rate_limit(request: Request, user_id: str = None) -> None:
    """
    Enforces sliding-window rate limiting per client IP or user ID.
    Rejects requests with HTTP 429 when threshold is reached.
    """
    client_ip = request.client.host if request.client else "unknown"
    key = f"{user_id or 'anon'}:{client_ip}"
    current_time = time.time()
    cutoff_time = current_time - WINDOW_SECONDS

    # Prune timestamps older than window
    timestamps = [t for t in _rate_limit_records[key] if t > cutoff_time]
    _rate_limit_records[key] = timestamps

    if len(timestamps) >= MAX_REQUESTS_PER_WINDOW:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Maximum 60 requests per minute allowed.",
            headers={"Retry-After": str(int(WINDOW_SECONDS))},
        )

    _rate_limit_records[key].append(current_time)