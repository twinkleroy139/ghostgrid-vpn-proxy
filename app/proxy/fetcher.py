from dataclasses import dataclass
from typing import Dict, Optional
from urllib.parse import urljoin, urlsplit, urlunsplit

from curl_cffi.requests import AsyncSession

from app.config.settings import get_settings
from app.proxy.cookie_manager import cookie_jar
from app.proxy.header_cleaner import sanitize_request_headers, sanitize_response_headers
from app.proxy.vpn_manager import vpn_manager
from app.security.sanitizer import sanitize_and_validate_target_url


class VPNUnavailableError(RuntimeError):
    """The requested VPN node could not be brought up. Do NOT fall back to direct."""


class UpstreamFetchError(RuntimeError):
    """A request to the upstream failed. Carries the layer (socks/dns/tls/http)."""

    def __init__(self, layer: str, url: str, cause: BaseException):
        self.layer = layer
        self.url = url
        self.cause = cause
        super().__init__(f"[{layer}] {cause.__class__.__name__}: {cause} (target={url})")


class ResponseTooLargeError(RuntimeError):
    """Upstream body exceeded MAX_RESPONSE_SIZE_BYTES."""


@dataclass
class ProxyFetchResult:
    status_code: int
    headers: Dict[str, str]
    content: bytes
    final_url: str
    content_type: str


def _split_fragment(url: str) -> tuple[str, str]:
    """Return (url_without_fragment, fragment_with_leading_hash_or_empty)."""
    parts = urlsplit(url)
    fragment = f"#{parts.fragment}" if parts.fragment else ""
    clean = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
    return clean, fragment


def _classify_error(exc: BaseException) -> str:
    """Map a curl_cffi/OSError exception into a layer tag for logs."""
    name = exc.__class__.__name__.lower()
    msg = str(exc).lower()
    if "socks" in name or "socks" in msg or "proxy" in msg:
        return "socks"
    if "dns" in name or "resolve" in msg or "getaddrinfo" in msg or "name or service" in msg:
        return "dns"
    if "ssl" in name or "tls" in name or "certificate" in msg:
        return "tls"
    if "timeout" in name or "timed out" in msg:
        return "timeout"
    return "http"


class ProxyFetcher:
    def __init__(self):
        self.settings = get_settings()

    async def fetch(
        self,
        target_url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        content: Optional[bytes] = None,
        user_id: str = "guest_operative",
        node: str = "direct",
    ) -> ProxyFetchResult:
        # --- resolve proxy (MUST succeed for non-direct nodes) ---
        proxy_mount = vpn_manager.get_active_node_proxy(node)
        if node != "direct" and not proxy_mount:
            raise VPNUnavailableError(
                f"VPN node '{node}' is not available (tunnel failed to start). "
                "Refusing to fall back to a direct connection."
            )

        # --- strip fragment from fetch target, keep it for the caller ---
        clean_url, fragment = _split_fragment(target_url)
        current_url = sanitize_and_validate_target_url(clean_url)

        incoming_headers = headers or {}
        redirect_count = 0
        size_cap = self.settings.MAX_RESPONSE_SIZE_BYTES

        async with AsyncSession(impersonate="chrome124") as session:
            while True:
                parsed = urlsplit(current_url)
                target_host = parsed.netloc
                clean_headers = sanitize_request_headers(
                    incoming_headers, target_host, method=method
                )

                stored_cookie = cookie_jar.get_cookie_header(user_id, current_url)
                if stored_cookie:
                    clean_headers["Cookie"] = stored_cookie

                try:
                    response = await session.request(
                        method=method,
                        url=current_url,
                        headers=clean_headers,
                        data=content if method in ("POST", "PUT", "PATCH") else None,
                        proxy=proxy_mount,
                        timeout=self.settings.REQUEST_TIMEOUT_SECONDS,
                        allow_redirects=False,
                        verify=True,
                    )
                except Exception as exc:
                    raise UpstreamFetchError(_classify_error(exc), current_url, exc) from exc

                raw_resp_headers = dict(response.headers)
                cookie_jar.save_response_cookies(user_id, current_url, raw_resp_headers)

                # --- redirect handling (unchanged logic, but each hop re-validated) ---
                if response.status_code in (301, 302, 303, 307, 308) and "location" in response.headers:
                    redirect_count += 1
                    if redirect_count > self.settings.MAX_REDIRECTS:
                        raise ValueError(
                            f"Exceeded maximum redirect limit ({self.settings.MAX_REDIRECTS})"
                        )
                    next_url = urljoin(current_url, response.headers["location"])
                    next_clean, _ = _split_fragment(next_url)
                    current_url = sanitize_and_validate_target_url(next_clean)
                    method = "GET"
                    content = None
                    continue

                raw_bytes = response.content
                if size_cap and len(raw_bytes) > size_cap:
                    raise ResponseTooLargeError(
                        f"Upstream response {len(raw_bytes)} bytes > cap {size_cap}"
                    )

                clean_resp_headers = sanitize_response_headers(raw_resp_headers)
                content_type = clean_resp_headers.get("content-type", "").lower()

                final_url = str(response.url) + fragment

                return ProxyFetchResult(
                    status_code=response.status_code,
                    headers=clean_resp_headers,
                    content=raw_bytes,
                    final_url=final_url,
                    content_type=content_type,
                )