import re
from bs4 import BeautifulSoup

from app.proxy.css_rewriter import rewrite_css
from app.proxy.js_injector import generate_client_interceptor_script
from app.proxy.url_encoder import resolve_proxied_url

SRCSET_REGEX = re.compile(r"([^\s,]+)(\s+[0-9.]+[wx])?")


def rewrite_srcset(base_url: str, srcset_value: str) -> str:
    """Rewrites comma-separated URLs within an image srcset attribute."""
    parts = []
    for item in srcset_value.split(","):
        trimmed = item.strip()
        if not trimmed:
            continue
        tokens = trimmed.split()
        if len(tokens) >= 1:
            img_url = tokens[0]
            proxied = resolve_proxied_url(base_url, img_url)
            descriptor = " " + tokens[1] if len(tokens) > 1 else ""
            parts.append(f"{proxied}{descriptor}")
    return ", ".join(parts)


def rewrite_html(html_bytes: bytes, base_url: str, encoding: str = "utf-8") -> str:
    """
    Parses HTML markup, rewrites links/images/forms/styles through GhostGrid,
    rewrites inline <style> tags, and injects the client-side JavaScript interceptor into <head>.
    """
    try:
        html_text = html_bytes.decode(encoding, errors="replace")
    except Exception:
        html_text = html_bytes.decode("utf-8", errors="replace")

    soup = BeautifulSoup(html_text, "lxml")

    # 1. Tags with href attribute
    for tag in soup.find_all(["a", "link", "area"], href=True):
        tag["href"] = resolve_proxied_url(base_url, tag["href"])

    # 2. Tags with src attribute
    for tag in soup.find_all(
        ["img", "script", "iframe", "source", "track", "audio", "video"], src=True
    ):
        tag["src"] = resolve_proxied_url(base_url, tag["src"])

    # 3. Responsive images with srcset
    for tag in soup.find_all(["img", "source"], srcset=True):
        tag["srcset"] = rewrite_srcset(base_url, tag["srcset"])

    # 4. Form actions (<form action="...">)
    for form in soup.find_all("form", action=True):
        form["action"] = resolve_proxied_url(base_url, form["action"])

    # 5. Inline CSS style attributes with url(...)
    for tag in soup.find_all(style=True):
        style_text = tag["style"]
        if "url(" in style_text:
            tag["style"] = re.sub(
                r'url\(\s*[\'"]?([^\'")]+)[\'"]?\s*\)',
                lambda m: f'url("{resolve_proxied_url(base_url, m.group(1))}")',
                style_text,
            )

    # 6. Inline <style> blocks (rewriting @import and url() via css_rewriter)
    for style_tag in soup.find_all("style"):
        if style_tag.string:
            style_tag.string = rewrite_css(style_tag.string, base_url)

    # 7. Inject JS interceptor script into <head> (or at the top if no head tag)
    interceptor_html = generate_client_interceptor_script(base_url)
    interceptor_soup = BeautifulSoup(interceptor_html, "html.parser")

    if soup.head:
        soup.head.insert(0, interceptor_soup)
    elif soup.body:
        soup.body.insert(0, interceptor_soup)
    else:
        soup.insert(0, interceptor_soup)

    return str(soup)