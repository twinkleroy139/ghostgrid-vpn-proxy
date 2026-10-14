import base64
from urllib.parse import urljoin, urlparse


def encode_url(url: str) -> str:
    """Encodes a target URL safely for URL path parameters using standard URL-safe Base64 without padding."""
    if not url:
        return ""
    raw_bytes = url.strip().encode("utf-8")
    return base64.urlsafe_b64encode(raw_bytes).decode("ascii").rstrip("=")


def decode_url(encoded_token: str) -> str:
    """Decodes a URL-safe Base64 token back to its original target URL."""
    if not encoded_token:
        return ""
    token = encoded_token.strip()
    padding_needed = len(token) % 4
    if padding_needed:
        token += "=" * (4 - padding_needed)

    try:
        decoded_bytes = base64.urlsafe_b64decode(token.encode("ascii"))
        return decoded_bytes.decode("utf-8")
    except Exception:
        return ""


def resolve_proxied_url(base_target_url: str, relative_or_absolute_url: str) -> str:
    """
    Resolves relative links (e.g., '/style.css', '../img.png') against the base target URL,
    and returns a GhostGrid proxy endpoint URL: /proxy/fetch?url=<encoded>.
    Preserves data URIs, javascript: links, and anchors untouched.
    """
    clean_target = relative_or_absolute_url.strip()

    if not clean_target:
        return ""

    lowered = clean_target.lower()
    if (
        lowered.startswith("data:")
        or lowered.startswith("javascript:")
        or lowered.startswith("blob:")
        or lowered.startswith("#")
        or lowered.startswith("mailto:")
        or lowered.startswith("tel:")
    ):
        return clean_target

    # Convert protocol-relative URLs like //example.com to https://example.com
    if clean_target.startswith("//"):
        parsed_base = urlparse(base_target_url)
        clean_target = f"{parsed_base.scheme or 'https'}:{clean_target}"

    # Resolve relative URL against current target URL
    absolute_url = urljoin(base_target_url, clean_target)

    # Encode absolute URL into GhostGrid route
    encoded = encode_url(absolute_url)
    return f"/proxy/fetch?url={encoded}"