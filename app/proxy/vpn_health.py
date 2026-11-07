"""
app/proxy/vpn_health.py

Standalone health probes for SOCKS5 listeners and end-to-end VPN tunnels.
No project imports — depends only on stdlib + curl_cffi (already required).
"""

import asyncio
import logging
import socket
import time
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger("ghostgrid.vpn.health")

# Small, fast, no-auth, stable endpoint used to prove the tunnel reaches the internet.
DEFAULT_PROBE_URL = "https://api.ipify.org"
DEFAULT_TIMEOUT = 15.0


def wait_for_port(host: str, port: int, timeout: float = DEFAULT_TIMEOUT) -> bool:
    """Block until TCP connect succeeds on host:port, or timeout. Returns True on success."""
    deadline = time.monotonic() + timeout
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        try:
            with socket.create_connection((host, port), timeout=1.0):
                logger.info("SOCKS5 listener ready on %s:%d after %d attempt(s)", host, port, attempt)
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.25)
    logger.error("SOCKS5 listener never came up on %s:%d within %.1fs", host, port, timeout)
    return False


def _parse_proxy(proxy_url: str) -> tuple[str, int]:
    p = urlparse(proxy_url)
    if not p.hostname or not p.port:
        raise ValueError(f"Invalid proxy URL: {proxy_url!r}")
    return p.hostname, p.port


async def probe_socks5(
    proxy_url: str,
    test_url: str = DEFAULT_PROBE_URL,
    timeout: float = DEFAULT_TIMEOUT,
) -> bool:
    """
    End-to-end check: perform a real HTTPS GET through the SOCKS5 proxy.
    Returns True if the upstream returns 2xx/3xx, False otherwise.
    Never raises — all failures are logged and converted to False.
    """
    # Imported lazily so this module loads even if curl_cffi is broken.
    try:
        from curl_cffi.requests import AsyncSession
    except Exception as exc:  # pragma: no cover
        logger.error("curl_cffi import failed: %s", exc)
        return False

    try:
        async with AsyncSession(impersonate="chrome124") as session:
            resp = await asyncio.wait_for(
                session.get(
                    test_url,
                    proxy=proxy_url,
                    timeout=timeout,
                    allow_redirects=False,
                ),
                timeout=timeout + 2.0,
            )
            ok = 200 <= resp.status_code < 400
            logger.info("probe_socks5 %s via %s -> %d (%s)",
                        test_url, proxy_url, resp.status_code, "OK" if ok else "FAIL")
            return ok
    except asyncio.TimeoutError:
        logger.error("probe_socks5 timeout after %.1fs via %s", timeout, proxy_url)
        return False
    except Exception as exc:
        logger.error("probe_socks5 exception via %s: %s: %s",
                     proxy_url, exc.__class__.__name__, exc)
        return False


async def check_node_health(
    proxy_url: Optional[str],
    *,
    probe_url: str = DEFAULT_PROBE_URL,
    timeout: float = DEFAULT_TIMEOUT,
    skip_end_to_end: bool = False,
) -> dict:
    """
    Composite health check used by /proxy/nodes and callers that need a structured result.
    Returns: {"configured": bool, "listening": bool, "reachable": bool|None, "error": str|None}
    - configured: proxy_url is non-empty
    - listening: SOCKS5 TCP port accepts connections
    - reachable: HTTP request through the proxy returned 2xx/3xx (None if skipped)
    """
    result = {"configured": False, "listening": False, "reachable": None, "error": None}

    if not proxy_url:
        result["error"] = "no proxy URL configured"
        return result

    result["configured"] = True

    try:
        host, port = _parse_proxy(proxy_url)
    except ValueError as exc:
        result["error"] = str(exc)
        return result

    # TCP port poll — do this in a thread so we don't block the event loop.
    loop = asyncio.get_running_loop()
    listening = await loop.run_in_executor(None, wait_for_port, host, port, timeout)
    result["listening"] = listening
    if not listening:
        result["error"] = f"SOCKS5 port {port} not listening"
        return result

    if not skip_end_to_end:
        result["reachable"] = await probe_socks5(proxy_url, probe_url, timeout)
        if not result["reachable"]:
            result["error"] = "tunnel up but upstream request failed"

    return result