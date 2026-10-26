from dataclasses import dataclass
from typing import Dict, Optional
from urllib.parse import urljoin, urlparse

from curl_cffi.requests import AsyncSession

from app.config.settings import get_settings
from app.proxy.cookie_manager import cookie_jar
from app.proxy.header_cleaner import sanitize_request_headers, sanitize_response_headers
from app.security.sanitizer import sanitize_and_validate_target_url


@dataclass
class ProxyFetchResult:
    status_code: int
    headers: Dict[str, str]
    content: bytes
    final_url: str
    content_type: str


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
        current_url = sanitize_and_validate_target_url(target_url)
        incoming_headers = headers or {}
        redirect_count = 0

        node_info = self.settings.available_nodes.get(node, self.settings.available_nodes["direct"])
        proxy_mount = node_info.get("url")

        async with AsyncSession(impersonate="chrome124") as session:
            while True:
                parsed = urlparse(current_url)
                target_host = parsed.netloc
                clean_headers = sanitize_request_headers(incoming_headers, target_host, method=method)

                stored_cookie = cookie_jar.get_cookie_header(user_id, current_url)
                if stored_cookie:
                    clean_headers["Cookie"] = stored_cookie

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

                raw_resp_headers = dict(response.headers)
                cookie_jar.save_response_cookies(user_id, current_url, raw_resp_headers)

                raw_bytes = response.content

                # Follow redirects with SSRF validation
                if response.status_code in (301, 302, 303, 307, 308) and "location" in response.headers:
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