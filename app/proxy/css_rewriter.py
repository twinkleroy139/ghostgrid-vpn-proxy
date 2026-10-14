import re
from app.proxy.url_encoder import resolve_proxied_url

# Regex to match url(...) declarations in CSS: url('path/to/asset.png') or url("...") or url(...)
CSS_URL_REGEX = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE)

# Regex to match @import statements: @import 'style.css'; or @import "style.css";
CSS_IMPORT_REGEX = re.compile(
    r"@import\s+(?:url\(\s*)?(['\"])(.*?)\1(?:\s*\))?", re.IGNORECASE
)


def rewrite_css(css_text: str, base_url: str) -> str:
    """
    Parses and rewrites CSS stylesheets.
    Rewrites all relative/absolute asset paths in url(...) and @import declarations
    to route through GhostGrid's /proxy/fetch endpoint.
    """
    if not css_text:
        return ""

    def replace_url(match: re.Match) -> str:
        quote = match.group(1) or '"'
        raw_target = match.group(2).strip()

        # Ignore data URIs or empty targets
        if not raw_target or raw_target.lower().startswith("data:"):
            return match.group(0)

        proxied = resolve_proxied_url(base_url, raw_target)
        return f"url({quote}{proxied}{quote})"

    def replace_import(match: re.Match) -> str:
        quote = match.group(1) or '"'
        raw_target = match.group(2).strip()

        if not raw_target or raw_target.lower().startswith("data:"):
            return match.group(0)

        proxied = resolve_proxied_url(base_url, raw_target)
        return f'@import {quote}{proxied}{quote}'

    # 1. Rewrite @import statements first
    rewritten = CSS_IMPORT_REGEX.sub(replace_import, css_text)

    # 2. Rewrite background, border-image, and @font-face url() references
    rewritten = CSS_URL_REGEX.sub(replace_url, rewritten)

    return rewritten