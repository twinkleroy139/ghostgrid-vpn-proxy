from typing import Optional
import httpx
from fastapi import APIRouter, Depends, Query, Request, Response, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse

from app.config.settings import get_settings
from app.middleware.auth import get_current_user
from app.middleware.error_handler import render_cyberpunk_error_page
from app.middleware.rate_limit import check_rate_limit
from app.proxy.cache_manager import asset_cache
from app.proxy.css_rewriter import rewrite_css
from app.proxy.fetcher import ProxyFetcher
from app.proxy.html_rewriter import rewrite_html
from app.proxy.stream_handler import stream_upstream_content
from app.proxy.url_encoder import decode_url
from app.proxy.ws_proxy import proxy_websocket
from app.security.adblock import is_ad_or_tracker
from app.services.history_service import history_service
from app.services.logger import log_proxy_access
from app.services.usage_service import usage_service

router = APIRouter(prefix="/proxy", tags=["Proxy Core"])
fetcher = ProxyFetcher()
settings = get_settings()


@router.get("/nodes")
async def list_vpn_nodes():
    """Returns available VPN / Egress connection nodes for the HUD dropdown."""
    nodes = [
        {"id": k, "name": v["name"], "configured": v["url"] is not None or k == "direct"}
        for k, v in settings.available_nodes.items()
    ]
    return JSONResponse(content={"nodes": nodes})


@router.api_route("/fetch", methods=["GET", "POST"])
async def proxy_fetch_endpoint(
    request: Request,
    url: str = Query(..., description="URL-safe Base64 encoded target URL"),
    node: str = Query("direct", description="Selected VPN egress node ID"),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user.get("uid", "guest_operative")

    try:
        check_rate_limit(request, user_id=user_id)
    except Exception as exc:
        return render_cyberpunk_error_page(429, "RATE CEILING BREACHED", str(exc))

    raw_target_url = decode_url(url)
    if not raw_target_url:
        return render_cyberpunk_error_page(400, "INVALID TARGET IDENTIFIER", "The target URL token was malformed.")

    if is_ad_or_tracker(raw_target_url):
        return Response(status_code=204)

    client_headers = dict(request.headers)

    # Partial Content & Video Streaming Pipeline
    if "range" in [k.lower() for k in client_headers.keys()]:
        try:
            node_url = settings.available_nodes.get(node, {}).get("url")
            async with httpx.AsyncClient(proxy=node_url, verify=True, follow_redirects=True) as stream_client:
                return await stream_upstream_content(
                    client=stream_client,
                    method=request.method,
                    target_url=raw_target_url,
                    headers=client_headers,
                )
        except Exception as exc:
            return render_cyberpunk_error_page(502, "STREAM TUNNEL COLLAPSE", str(exc), raw_target_url)

    # Asset Cache Lookup
    cache_key = f"{node}:{raw_target_url}"
    if request.method == "GET":
        cached_result = asset_cache.get(cache_key)
        if cached_result:
            content_bytes, c_type = cached_result
            log_proxy_access(user_id, raw_target_url, 200, len(content_bytes))
            return Response(content=content_bytes, media_type=c_type)

    try:
        body_bytes: Optional[bytes] = None
        if request.method in ("POST", "PUT", "PATCH"):
            body_bytes = await request.body()

        result = await fetcher.fetch(
            target_url=raw_target_url,
            method=request.method,
            headers=client_headers,
            content=body_bytes,
            user_id=user_id,
            node=node,
        )

        content_type = result.content_type
        payload_size = len(result.content)

        usage_service.record_usage(user_id, payload_size)
        log_proxy_access(user_id, result.final_url, result.status_code, payload_size)

        # HTML Processing & DOM Rewriting
        if "text/html" in content_type:
            history_service.add_entry(user_id, result.final_url)
            rewritten_html = rewrite_html(result.content, result.final_url, node=node)
            return HTMLResponse(
                content=rewritten_html,
                status_code=result.status_code,
                headers=result.headers,
            )

        # CSS Stylesheet Processing
        if "text/css" in content_type:
            try:
                css_text = result.content.decode("utf-8", errors="replace")
                rewritten_css = rewrite_css(css_text, result.final_url).encode("utf-8")
                asset_cache.set(cache_key, rewritten_css, "text/css")
                return Response(
                    content=rewritten_css,
                    status_code=result.status_code,
                    headers=result.headers,
                    media_type="text/css",
                )
            except Exception:
                pass

        if any(t in content_type for t in ("image/", "font/", "javascript", "application/json")):
            asset_cache.set(cache_key, result.content, content_type)

        return Response(
            content=result.content,
            status_code=result.status_code,
            headers=result.headers,
            media_type=content_type if content_type else "application/octet-stream",
        )

    except ValueError as val_err:
        return render_cyberpunk_error_page(403, "SECURITY DIRECTIVE VIOLATION", str(val_err), raw_target_url)
    except Exception as exc:
        return render_cyberpunk_error_page(502, "UPSTREAM PROXY EXCEPTION", str(exc), raw_target_url)


@router.websocket("/ws")
async def proxy_ws_endpoint(
    websocket: WebSocket,
    url: str = Query(..., description="URL-safe Base64 encoded target WebSocket URL"),
):
    raw_ws_url = decode_url(url)
    if not raw_ws_url:
        await websocket.close(code=1008)
        return
    await proxy_websocket(websocket, raw_ws_url)