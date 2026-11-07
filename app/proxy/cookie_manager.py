"""
app/proxy/cookie_manager.py

Per-user, per-domain HTTP cookie jar for the proxy.

Stores the full morsel (attributes included) so:
  - Path scoping is respected
  - Domain cookies (.example.com) share to subdomains
  - Secure cookies only go over HTTPS
  - Expires / Max-Age are honored
  - Set-Cookie with empty value / past expiry correctly deletes

Known limitations (documented, not blockers for production):
  - In-memory only. Render restart = all user sessions reset.
  - No HttpOnly enforcement — we are a proxy; cookies we replay are sent
    from the backend, not the browser, so HttpOnly is informational only.
  - No SameSite enforcement — same reason.
  - No PSL (public suffix list) — a cookie for Domain=.com would be replayed
    to any *.com host. Real browsers reject such cookies; we do not. This is
    a per-site correctness issue, not a security issue (the proxy is the only
    client), but worth noting.
"""

import time
from http.cookies import SimpleCookie
from typing import Dict, List, Optional
from urllib.parse import urlparse


def _domain_matches(cookie_domain: str, request_host: str) -> bool:
    """True if the request host is covered by the cookie's domain."""
    cd = cookie_domain.lstrip(".").lower()
    rh = request_host.lower()
    return rh == cd or rh.endswith("." + cd)


def _path_matches(cookie_path: str, request_path: str) -> bool:
    """RFC 6265: cookie path must be a prefix of the request path."""
    if not cookie_path or cookie_path == "/":
        return True
    if request_path == cookie_path:
        return True
    if request_path.startswith(cookie_path):
        # Prevent /foo matching /foobar (require slash after prefix)
        if len(request_path) == len(cookie_path) or request_path[len(cookie_path)] == "/":
            return True
    return False


class CookieManager:
    def __init__(self):
        # { user_id: { "domain|path|name": record } }
        self._jars: Dict[str, Dict[str, dict]] = {}

    # ------------------------------------------------------------------ helpers
    def _extract_host_path(self, url: str) -> tuple[str, str, bool]:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        path = parsed.path or "/"
        is_https = parsed.scheme.lower() == "https"
        return host, path, is_https

    def _is_expired(self, record: dict, now: Optional[float] = None) -> bool:
        exp = record.get("expires")
        if exp is None:
            return False
        return (now if now is not None else time.time()) >= exp

    # ------------------------------------------------------------------ write
    def save_response_cookies(
        self, user_id: str, target_url: str, raw_headers: Dict[str, str]
    ) -> None:
        """Parse all Set-Cookie headers and update the jar."""
        host, req_path, _ = self._extract_host_path(target_url)
        if not host:
            return

        self._jars.setdefault(user_id, {})
        jar = self._jars[user_id]

        for key, val in raw_headers.items():
            if key.lower() != "set-cookie":
                continue
            parser = SimpleCookie()
            try:
                parser.load(val)
            except Exception:
                continue

            for name, morsel in parser.items():
                domain_attr = (morsel.get("domain") or "").strip()
                # Default: host-only cookie (no leading dot)
                effective_domain = domain_attr.lstrip(".") if domain_attr else host
                is_host_only = not domain_attr

                path_attr = morsel.get("path") or "/"
                secure = bool(morsel.get("secure"))

                # Expiry
                expires_at: Optional[float] = None
                max_age = morsel.get("max-age")
                if max_age is not None:
                    try:
                        expires_at = time.time() + int(max_age)
                    except (ValueError, TypeError):
                        expires_at = None
                elif morsel.get("expires"):
                    try:
                        from email.utils import parsedate_to_datetime
                        dt = parsedate_to_datetime(morsel["expires"])
                        expires_at = dt.timestamp()
                    except Exception:
                        expires_at = None

                key_id = f"{effective_domain}|{path_attr}|{name}"

                # Deletion semantics: empty value + past expiry (or max-age=0)
                is_delete = (
                    morsel.value == ""
                    and (expires_at is not None and expires_at <= time.time())
                ) or (max_age is not None and max_age.strip() == "0")

                if is_delete:
                    jar.pop(key_id, None)
                    continue

                jar[key_id] = {
                    "name": name,
                    "value": morsel.value,
                    "domain": effective_domain,
                    "host_only": is_host_only,
                    "path": path_attr,
                    "secure": secure,
                    "expires": expires_at,
                    "httponly": bool(morsel.get("httponly")),
                    "samesite": (morsel.get("samesite") or "").lower(),
                }

    # ------------------------------------------------------------------ read
    def get_cookie_header(self, user_id: str, target_url: str) -> Optional[str]:
        """
        Return a Cookie header string for the given URL, or None.
        Applies domain, path, secure, and expiry rules.
        """
        if user_id not in self._jars:
            return None

        host, req_path, is_https = self._extract_host_path(target_url)
        if not host:
            return None

        jar = self._jars[user_id]
        now = time.time()
        matches: List[dict] = []
        expired_keys: List[str] = []

        for key_id, rec in jar.items():
            if self._is_expired(rec, now):
                expired_keys.append(key_id)
                continue

            # Host-only cookies: exact host match only. Domain cookies: suffix match.
            if rec.get("host_only"):
                if host != rec["domain"]:
                    continue
            elif not _domain_matches(rec["domain"], host):
                continue

            if not _path_matches(rec.get("path") or "/", req_path):
                continue
            if rec.get("secure") and not is_https:
                continue
            matches.append(rec)

        # Evict expired
        for k in expired_keys:
            jar.pop(k, None)

        if not matches:
            return None

        # Longest path first (RFC 6265 §5.4 ordering)
        matches.sort(key=lambda r: -len(r.get("path") or "/"))
        return "; ".join(f"{r['name']}={r['value']}" for r in matches)

    # ------------------------------------------------------------------ lifecycle
    def clear_user_cookies(self, user_id: str) -> None:
        self._jars.pop(user_id, None)


cookie_jar = CookieManager()