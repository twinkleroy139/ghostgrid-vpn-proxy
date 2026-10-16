from dataclasses import dataclass
from typing import Dict, Optional
from urllib.parse import urljoin, urlparse

import httpx

from app.config.settings import get_settings
from app.proxy.cookie_manager import cookie_jar
from app.proxy.header_cleaner import sanitize_request_headers, sanitize_response_headers
from app.security.sanitizer import sanitize_and_validate_target_url


@dataclass
class ProxyFetchResult:
    """Holds the result of a fetched upstream web resource."""

    status_code: int
    headers: Dict[str, str]
    content: bytes
    final_url: str
    content_type: str


class ProxyFetcher:
    """Async HTTP engine with multi-hop SSRF validation and redirect loop containment."""

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
        """
        Fetches an upstream target URL asynchronously.
        Routes through the chosen egress node and enforces SSRF / redirect constraints.
        """
        current_url = sanitize_and_validate_target_url(target_url)
        incoming_headers = headers or {}
        redirect_count = 0

        # Resolve upstream proxy URL for selected node
        node_info = self.settings.available_nodes.get(node, self.settings.available_nodes["direct"])
        proxy_mount = node_info.get("url")

        async with httpx.AsyncClient(
            proxy=proxy_mount,
            follow_redirects=False,
            timeout=httpx.Timeout(self.settings.REQUEST_TIMEOUT_SECONDS, connect=10.0),
            verify=True,
            http2=True,
        ) as client:
            while True:
                parsed = urlparse(current_url)
                target_host = parsed.netloc
                clean_headers = sanitize_request_headers(incoming_headers, target_host)

                # Attach domain cookies if available
                stored_cookie = cookie_jar.get_cookie_header(user_id, current_url)
                if stored_cookie:
                    clean_headers["Cookie"] = stored_cookie

                response = await client.request(
                    method=method,
                    url=current_url,
                    headers=clean_headers,
                    content=content if method in ("POST", "PUT", "PATCH") else None,
                )

                # Store incoming cookies from response
                raw_resp_headers = dict(response.headers)
                cookie_jar.save_response_cookies(user_id, current_url, raw_resp_headers)

                raw_bytes = response.content
                if len(raw_bytes) > self.settings.MAX_RESPONSE_SIZE_BYTES:
                    raise ValueError(
                        f"Target response size ({len(raw_bytes)} bytes) exceeds limit of "
                        f"{self.settings.MAX_RESPONSE_SIZE_BYTES} bytes."
                    )

                # Manual redirect handling with SSRF re-verification
                if response.is_redirect and "location" in response.headers:
                    redirect_count += 1
                    if redirect_count > self.settings.MAX_REDIRECTS:
                        raise ValueError(f"Exceeded maximum redirect limit ({self.settings.MAX_REDIRECTS})")

                    location = response.headers["location"]
                    next_url = urljoin(current_url, location)

                    current_url = sanitize_and_validate_target_url(next_url)
                    method = "GET"
                    content = None
                    continue

                clean_resp_headers = sanitize_response_headers(raw_resp_headers)
                content_type = clean_resp_headers.get("content-type", "").lower()

                return ProxyFetchResult(
                    status_code=response.status_code,
                    headers=clean_resp_headers,
                    content=raw_bytes,
                    final_url=str(response.url),
                    content_type=content_type,
                )