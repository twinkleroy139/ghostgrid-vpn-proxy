import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse

from app.config.settings import get_settings
from app.middleware.auth import get_current_user
from app.middleware.error_handler import render_cyberpunk_error_page
from app.middleware.rate_limit import check_rate_limit
from app.proxy.cache_manager import asset_cache
from app.proxy.css_rewriter import rewrite_css
from app.proxy.fetcher import (
    ProxyFetcher,
    ResponseTooLargeError,
    UpstreamFetchError,
    VPNUnavailableError,
)
from app.proxy.html_rewriter import rewrite_html_links
from app.proxy.shim import inject_into_html
from app.proxy.stream_handler import stream_upstream_content
from app.proxy.url_encoder import decode_url
from app.proxy.vpn_manager import vpn_manager
from app.proxy.ws_proxy import proxy_websocket
from app.security.adblock import is_ad_or_tracker
from app.services.history_service import history_service  # noqa: F401
from app.services.logger import log_proxy_access
from app.services.usage_service import usage_service

logger = logging.getLogger("ghostgrid.proxy.routes")

router = APIRouter(prefix="/proxy", tags=["Proxy Core"])
fetcher = ProxyFetcher()
settings = get_settings()


def _quiet_js_bypass(url: str, payload: bytes = b"/* GhostGrid bypassed */") -> Response:
    """Return a harmless JS body when a .js asset is rejected (SSRF / error)."""
    if url.endswith(".js") or "javascript" in url:
        return Response(content=payload, media_type="application/javascript")
    return None  # type: ignore[return-value]


@router.get("/nodes")
async def list_vpn_nodes():
    import os
    from pathlib import Path
    from app.proxy.vpn_manager import vpn_manager
    
    nodes = []
    for k, v in settings.available_nodes.items():
        # A node is configured if it has an env var URL, OR it's the WireGuard node with a valid config file
        is_configured = v["url"] is not None or k == "direct"
        
        if k == "us":
            # Check if proton_us.conf exists in any of the expected locations
            conf_paths = [
                vpn_manager.vpn_dir / "proton_us.conf",
                Path("/etc/secrets/proton_us.conf"),
                vpn_manager.base_dir / "proton_us.conf"
            ]
            if any(p.exists() for p in conf_paths):
                is_configured = True

        nodes.append({"id": k, "name": v["name"], "configured": is_configured})
        
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
        return render_cyberpunk_error_page(
            400, "INVALID TARGET IDENTIFIER", "The target URL token was malformed."
        )

    if is_ad_or_tracker(raw_target_url) or "accounts.google.com/ServiceLogin" in raw_target_url:
        return Response(status_code=204)

    if raw_target_url.endswith(".map"):
        return Response(status_code=204)

    client_headers = dict(request.headers)

    # --------------------------------------------------------------- STREAM PATH
    if "range" in [k.lower() for k in client_headers.keys()]:
        proxy_url = vpn_manager.get_active_node_proxy(node)
        if node != "direct" and not proxy_url:
            return render_cyberpunk_error_page(
                503,
                "VPN TUNNEL OFFLINE",
                f"Stream request for node '{node}' blocked: tunnel not ready.",
                raw_target_url,
            )

        from curl_cffi.requests import AsyncSession

        try:
            async with AsyncSession(impersonate="chrome124") as stream_session:
                return await stream_upstream_content(
                    client=stream_session,
                    method=request.method,
                    target_url=raw_target_url,
                    headers=client_headers,
                    proxy=proxy_url,
                )
        except VPNUnavailableError as exc:
            logger.error(
                "proxy_stream fail node=%s url=%s cls=%s msg=%s",
                node, raw_target_url, exc.__class__.__name__, exc,
            )
            return render_cyberpunk_error_page(503, "VPN TUNNEL OFFLINE", str(exc), raw_target_url)
        except Exception as exc:
            logger.error(
                "proxy_stream fail node=%s url=%s cls=%s msg=%s",
                node, raw_target_url, exc.__class__.__name__, exc,
            )
            return render_cyberpunk_error_page(502, "STREAM TUNNEL COLLAPSE", str(exc), raw_target_url)

    # --------------------------------------------------------------- CACHE LOOKUP
    cache_key = f"{node}:{raw_target_url}"
    if request.method == "GET":
        cached_result = asset_cache.get(cache_key)
        if cached_result:
            content_bytes, c_type = cached_result
            log_proxy_access(user_id, raw_target_url, 200, len(content_bytes))
            return Response(content=content_bytes, media_type=c_type)

    # --------------------------------------------------------------- FETCH PATH
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

        # Cache safe asset types only. NOTE: text/css deliberately excluded —
        # CSS must be rewritten on every request, so we do not cache the raw body.
        if result.status_code == 200 and any(
            t in content_type for t in
            ("image/", "font/", "javascript", "application/json")
        ):
            asset_cache.set(cache_key, result.content, content_type)

        # ------------------------------------------------------- CSS RESPONSE
        if "text/css" in content_type:
            css_text = result.content.decode("utf-8", errors="replace")
            proxy_origin = str(request.base_url).rstrip("/")
            try:
                css_text = rewrite_css(
                    css_text, result.final_url, node, proxy_origin=proxy_origin
                )
            except Exception as exc:
                logger.warning(
                    "css_rewriter fail url=%s cls=%s msg=%s (serving raw)",
                    result.final_url, exc.__class__.__name__, exc,
                )
            headers = {
                k: v for k, v in result.headers.items()
                if k.lower() not in ("cache-control", "etag", "last-modified")
            }
            headers["Cache-Control"] = "no-store"
            return Response(
                content=css_text.encode("utf-8"),
                status_code=result.status_code,
                headers=headers,
                media_type="text/css",
            )

        # ------------------------------------------------------- HTML RESPONSE
        if "text/html" in content_type:
            html_text = result.content.decode("utf-8", errors="replace")
            proxy_origin = str(request.base_url).rstrip("/")

            try:
                html_text = rewrite_html_links(
                    html_text, result.final_url, node, proxy_origin=proxy_origin
                )
            except Exception as exc:
                logger.warning(
                    "rewriter fail url=%s cls=%s msg=%s (falling back to shim only)",
                    result.final_url, exc.__class__.__name__, exc,
                )

            html_text = inject_into_html(html_text, result.final_url, node)

            headers = {
                k: v for k, v in result.headers.items()
                if k.lower() not in ("cache-control", "etag", "last-modified")
            }
            headers["Cache-Control"] = "no-store"
            return HTMLResponse(content=html_text, status_code=result.status_code, headers=headers)

        # ------------------------------------------------------- BINARY RESPONSE
        return Response(
            content=result.content,
            status_code=result.status_code,
            headers=result.headers,
            media_type=content_type if content_type else "application/octet-stream",
        )

    # --------------------------------------------------------------- ERRORS
    except VPNUnavailableError as exc:
        logger.error(
            "proxy_fetch fail node=%s url=%s cls=%s msg=%s",
            node, raw_target_url, exc.__class__.__name__, exc,
        )
        if raw_target_url.endswith(".js") or "javascript" in raw_target_url:
            return _quiet_js_bypass(raw_target_url, b"/* VPN bypassed */")
        return render_cyberpunk_error_page(
            503, "VPN TUNNEL OFFLINE",
            f"Node '{node}' is not reachable. Try again in a few seconds.",
            raw_target_url,
        )

    except UpstreamFetchError as exc:
        logger.error(
            "proxy_fetch fail node=%s url=%s cls=%s layer=%s msg=%s",
            node, raw_target_url, exc.__class__.__name__, exc.layer, exc,
        )
        if raw_target_url.endswith(".js") or "javascript" in raw_target_url:
            return _quiet_js_bypass(raw_target_url, b"/* upstream fetch failed */")
        return render_cyberpunk_error_page(
            502,
            f"UPSTREAM FAILED [{exc.layer.upper()}]",
            f"Target unreachable via node '{node}'. Layer: {exc.layer}.",
            raw_target_url,
        )

    except ResponseTooLargeError as exc:
        logger.error(
            "proxy_fetch fail node=%s url=%s cls=%s msg=%s",
            node, raw_target_url, exc.__class__.__name__, exc,
        )
        return render_cyberpunk_error_page(
            413, "RESPONSE EXCEEDS LIMIT",
            "Upstream payload is larger than the configured cap.",
            raw_target_url,
        )

    except ValueError as val_err:
        logger.warning(
            "proxy_fetch blocked node=%s url=%s cls=%s msg=%s",
            node, raw_target_url, val_err.__class__.__name__, val_err,
        )
        if raw_target_url.endswith(".js") or "javascript" in raw_target_url:
            return _quiet_js_bypass(raw_target_url, b"/* Script bypassed by security policy */")
        return render_cyberpunk_error_page(
            403, "SECURITY DIRECTIVE VIOLATION", str(val_err), raw_target_url
        )

    except Exception as exc:
        logger.error(
            "proxy_fetch fail node=%s url=%s cls=%s msg=%s",
            node, raw_target_url, exc.__class__.__name__, exc,
            exc_info=True,
        )
        if raw_target_url.endswith(".js") or "javascript" in raw_target_url:
            return _quiet_js_bypass(raw_target_url, b"/* Script load exception */")
        return render_cyberpunk_error_page(
            502, "UPSTREAM PROXY EXCEPTION",
            f"{exc.__class__.__name__}: {exc}",
            raw_target_url,
        )


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