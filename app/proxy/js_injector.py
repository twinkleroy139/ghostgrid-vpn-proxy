def generate_client_interceptor_script(base_url: str, node: str = "direct") -> str:
    return f"""
<script id="ghostgrid-interceptor">
(function() {{
    const TARGET_BASE_URL = "{base_url}";
    const CURRENT_NODE = "{node}";

    function encodeTarget(url) {{
        if (!url) return "";
        try {{
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
        return "/proxy/fetch?url=" + encodeTarget(url) + "&node=" + encodeURIComponent(CURRENT_NODE);
    }}

    // 1. Intercept window.fetch
    const originalFetch = window.fetch;
    window.fetch = function(resource, init) {{
        if (typeof resource === "string") {{
            resource = proxyUrl(resource);
        }} else if (resource instanceof Request) {{
            resource = new Request(proxyUrl(resource.url), resource);
        }}
        return originalFetch.call(this, resource, init);
    }};

    // 2. Intercept XMLHttpRequest
    const originalOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url, ...args) {{
        return originalOpen.call(this, method, proxyUrl(url), ...args);
    }};

    // 3. Intercept navigator.sendBeacon (prevents /error_204 404s)
    if (navigator.sendBeacon) {{
        const origSendBeacon = navigator.sendBeacon;
        navigator.sendBeacon = function(url, data) {{
            try {{
                return origSendBeacon.call(this, proxyUrl(url), data);
            }} catch(e) {{
                return true;
            }}
        }};
    }}

    // 4. Intercept dynamic Script & Link element URLs
    const origSetAttribute = Element.prototype.setAttribute;
    Element.prototype.setAttribute = function(name, val) {{
        if ((name === "src" || name === "href") && typeof val === "string") {{
            val = proxyUrl(val);
        }}
        return origSetAttribute.call(this, name, val);
    }};

    // 5. Neutralize ServiceWorker registrations in sandbox
    if (navigator.serviceWorker) {{
        navigator.serviceWorker.register = function() {{
            return Promise.reject(new Error("[GhostGrid] ServiceWorkers isolated."));
        }};
    }}

    // 6. Form submissions
    document.addEventListener("submit", function(e) {{
        const form = e.target;
        if (form && form.action && !form.action.includes("/proxy/fetch?url=")) {{
            form.action = proxyUrl(form.action);
        }}
    }}, true);

    console.log("[GhostGrid] Interceptor Active for: " + TARGET_BASE_URL);
}})();
</script>
"""