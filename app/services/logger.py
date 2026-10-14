import logging
from urllib.parse import urlparse

# Configure structured console logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [GHOSTGRID] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("ghostgrid.audit")


def log_proxy_access(user_id: str, target_url: str, status_code: int, bytes_transferred: int) -> None:
    """
    Privacy-first proxy logger.
    Logs only the hostname/domain and status code, never full URLs with query parameters or body payloads.
    """
    parsed = urlparse(target_url)
    domain = parsed.hostname or "unknown_target"
    logger.info(
        "OPERATIVE=%s DOMAIN=%s STATUS=%s BYTES=%s",
        user_id,
        domain,
        status_code,
        bytes_transferred,
    )