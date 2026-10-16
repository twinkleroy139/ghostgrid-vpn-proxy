import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse

from app.proxy.css_rewriter import rewrite_css
from app.proxy.js_injector import generate_client_interceptor_script
from app.proxy.url_encoder import resolve_proxied_url


def rewrite_srcset(base_url: str, srcset_value: str, node: str = "direct") -> str:
    parts = []
    for item in srcset_value.split(","):
        trimmed = item.strip()
        if not trimmed:
            continue
        tokens = trimmed.split()
        if len(tokens) >= 1:
            img_url = tokens[0]
            proxied = resolve_proxied_url(base_url, img_url) + f"&node={node}"
            descriptor = " " + tokens[1] if len(tokens) > 1 else ""
            parts.append(f"{proxied}{descriptor}")
    return ", ".join(parts)


def rewrite_html(html_bytes: bytes, base_url: str, encoding: str = "utf-8", node: str = "direct") -> str:
    try:
        html_text = html_bytes.decode(encoding, errors="replace")
    except Exception:
        html_text = html_bytes.decode("utf-8", errors="replace")

    soup = BeautifulSoup(html_text, "lxml")

    # 1. Tags with href attribute
    for tag in soup.find_all(["a", "link", "area"], href=True):
        tag["href"] = resolve_proxied_url(base_url, tag["href"]) + f"&node={node}"

    # 2. Tags with src attribute
    for tag in soup.find_all(
        ["img", "script", "iframe", "source", "track", "audio", "video"], src=True
    ):
        tag["src"] = resolve_proxied_url(base_url, tag["src"]) + f"&node={node}"

    # 3. Responsive images with srcset
    for tag in soup.find_all(["img", "source"], srcset=True):
        tag["srcset"] = rewrite_srcset(base_url, tag["srcset"], node=node)

    # 4. Form actions
    for form in soup.find_all("form", action=True):
        form["action"] = resolve_proxied_url(base_url, form["action"]) + f"&node={node}"

    # 5. Inline CSS style attributes
    for tag in soup.find_all(style=True):
        style_text = tag["style"]
        if "url(" in style_text:
            tag["style"] = re.sub(
                r'url\(\s*[\'"]?([^\'")]+)[\'"]?\s*\)',
                lambda m: f'url("{resolve_proxied_url(base_url, m.group(1))}&node={node}")',
                style_text,
            )

    # 6. Inline <style> blocks
    for style_tag in soup.find_all("style"):
        if style_tag.string:
            style_tag.string = rewrite_css(style_tag.string, base_url)

    # 7. Inject JS interceptor script into <head>
    interceptor_html = generate_client_interceptor_script(base_url, node=node)
    interceptor_soup = BeautifulSoup(interceptor_html, "html.parser")

    if soup.head:
        soup.head.insert(0, interceptor_soup)
    elif soup.body:
        soup.body.insert(0, interceptor_soup)
    else:
        soup.insert(0, interceptor_soup)

    return str(soup)