from typing import AsyncGenerator, Dict, Optional

import httpx
from fastapi.responses import StreamingResponse

from app.config.settings import get_settings
from app.proxy.header_cleaner import sanitize_request_headers, sanitize_response_headers


async def stream_upstream_content(
    client,
    method: str,
    target_url: str,
    headers: Dict[str, str],
    chunk_size: int = 65536,
    proxy: Optional[str] = None,
) -> StreamingResponse:
    """
    Streams large media files, videos, audio, and Range requests (HTTP 206)
    directly to the browser without buffering. `client` is a curl_cffi.AsyncSession
    when `proxy` is set (VPN path), else an httpx.AsyncClient (legacy).
    """
    settings = get_settings()
    parsed_target = httpx.URL(target_url)
    clean_req_headers = sanitize_request_headers(headers, parsed_target.host)

    if "range" in [k.lower() for k in headers.keys()]:
        for k, v in headers.items():
            if k.lower() == "range":
                clean_req_headers["Range"] = v
                break

    # curl_cffi path (VPN) — response exposes .iter_content()
    if proxy is not None:
        response = await client.request(
            method=method,
            url=target_url,
            headers=clean_req_headers,
            proxy=proxy,
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
            allow_redirects=True,
            stream=True,
        )
        clean_resp_headers = sanitize_response_headers(dict(response.headers))
        for h in ("content-range", "accept-ranges"):
            if h in response.headers:
                clean_resp_headers[h] = response.headers[h]

        async def content_iterator() -> AsyncGenerator[bytes, None]:
            try:
                async for chunk in response.aiter_content(chunk_size=chunk_size):
                    yield chunk
            finally:
                await response.aclose()

        return StreamingResponse(
            content_iterator(),
            status_code=response.status_code,
            headers=clean_resp_headers,
            media_type=response.headers.get("content-type", "application/octet-stream"),
        )

    # Legacy httpx path (kept for compatibility; not used by routes now)
    req = client.build_request(method=method, url=target_url, headers=clean_req_headers)
    response = await client.send(req, stream=True)
    clean_resp_headers = sanitize_response_headers(dict(response.headers))
    for h in ("content-range", "accept-ranges"):
        if h in response.headers:
            clean_resp_headers[h] = response.headers[h]

    async def content_iterator() -> AsyncGenerator[bytes, None]:
        try:
            async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                yield chunk
        finally:
            await response.aclose()

    return StreamingResponse(
        content_iterator(),
        status_code=response.status_code,
        headers=clean_resp_headers,
        media_type=response.headers.get("content-type", "application/octet-stream"),
    )