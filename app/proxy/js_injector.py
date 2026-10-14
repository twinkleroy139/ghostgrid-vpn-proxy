def generate_client_interceptor_script(base_url: str) -> str:
    """
    Generates inline JavaScript that is injected into proxied HTML pages.
    Patches:
    1. window.fetch() to intercept AJAX requests and redirect them via GhostGrid.
    2. XMLHttpRequest.prototype.open() for legacy dynamic calls.
    3. Form submission events to ensure form actions route through the proxy.
    """
    return f"""
<script id="ghostgrid-interceptor">
(function() {{
    const TARGET_BASE_URL = "{base_url}";

    // URL-safe Base64 encoder in client sandbox
    function encodeTarget(url) {{
        if (!url) return "";
        try {{
            // Resolve relative path against current target origin
            const resolved = new URL(url, TARGET_BASE_URL).href;
            const utf8 = new TextEncoder().encode(resolved);
            let bin = "";
            utf8.forEach(b => bin += String.fromCharCode(b));
            return btoa(bin).replace(/\\+/g, "-").replace(/\\//g, "_").replace(/=+$/, "");
        }} catch(e) {{
            return url;
        }}
    }}

    function proxyUrl(url) {{
        if (typeof url !== "string") return url;
        const low = url.toLowerCase().trim();
        if (low.startsWith("data:") || low.startsWith("blob:") || low.startsWith("javascript:")) return url;
        if (url.includes("/proxy/fetch?url=")) return url;
        return "/proxy/fetch?url=" + encodeTarget(url);
    }}

    // 1. Monkey-patch window.fetch
    const originalFetch = window.fetch;
    window.fetch = function(resource, init) {{
        if (typeof resource === "string") {{
            resource = proxyUrl(resource);
        }} else if (resource instanceof Request) {{
            resource = new Request(proxyUrl(resource.url), resource);
        }}
        return originalFetch.call(this, resource, init);
    }};

    // 2. Monkey-patch XMLHttpRequest
    const originalOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url, ...args) {{
        return originalOpen.call(this, method, proxyUrl(url), ...args);
    }};

    // 3. Intercept dynamic form submissions created via script
    document.addEventListener("submit", function(e) {{
        const form = e.target;
        if (form && form.action && !form.action.includes("/proxy/fetch?url=")) {{
            form.action = proxyUrl(form.action);
        }}
    }}, true);

    console.log("[GhostGrid] Client Runtime Interceptor Active for: " + TARGET_BASE_URL);
}})();
</script>
"""