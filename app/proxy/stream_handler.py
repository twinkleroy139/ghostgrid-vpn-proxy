from typing import AsyncGenerator, Dict
import httpx
from fastapi.responses import StreamingResponse

from app.config.settings import get_settings
from app.proxy.header_cleaner import sanitize_request_headers, sanitize_response_headers


async def stream_upstream_content(
    client: httpx.AsyncClient,
    method: str,
    target_url: str,
    headers: Dict[str, str],
    chunk_size: int = 65536,  # 64 KB streaming buffer
) -> StreamingResponse:
    """
    Streams large media files, videos, audio, and partial-range requests (HTTP 206)
    directly to the browser without buffering entire files in server memory.
    """
    settings = get_settings()
    parsed_target = httpx.URL(target_url)
    clean_req_headers = sanitize_request_headers(headers, parsed_target.host)

    # Forward byte Range header if the client browser requested it (for video seeking)
    if "range" in [k.lower() for k in headers.keys()]:
        for k, v in headers.items():
            if k.lower() == "range":
                clean_req_headers["Range"] = v
                break

    req = client.build_request(method=method, url=target_url, headers=clean_req_headers)
    response = await client.send(req, stream=True)

    clean_resp_headers = sanitize_response_headers(dict(response.headers))

    # Retain range headers necessary for video seek bars
    for h in ("content-range", "accept-ranges", "content-length"):
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