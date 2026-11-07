/**
 * GhostGrid Client-Side Service Worker (v4)
 *
 * Responsibilities:
 *   - Tunnel cross-origin subresource fetches through /proxy/fetch so they
 *     inherit the selected VPN node.
 *   - Remap same-origin requests that came from a proxied page (e.g. a CSS
 *     file requesting /static/fonts/a.ttf) to the real upstream via the proxy.
 *   - Never intercept top-level navigations (browsers don't allow it anyway).
 *   - Never intercept GhostGrid's own routes (/proxy/*, /sw.js).
 *   - Idempotent: never wrap a URL that is already /proxy/fetch?url=...
 */

const PROXY_ENDPOINT = "/proxy/fetch";
const SELF_PREFIXES = ["/proxy/", "/sw.js", "/favicon.ico"];
const MAX_SW_BODY_BYTES = 10 * 1024 * 1024;

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

function b64urlEncode(str) {
  const utf8 = new TextEncoder().encode(str);
  let bin = "";
  utf8.forEach((b) => (bin += String.fromCharCode(b)));
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function b64urlDecode(token) {
  try {
    let b64 = token.replace(/-/g, "+").replace(/_/g, "/");
    while (b64.length % 4) b64 += "=";
    const bin = atob(b64);
    const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
    return new TextDecoder().decode(bytes);
  } catch (_) {
    return null;
  }
}

function parseProxyUrl(urlObj) {
  try {
    if (urlObj.pathname !== PROXY_ENDPOINT) return null;
    const token = urlObj.searchParams.get("url");
    if (!token) return null;
    const decoded = b64urlDecode(token);
    if (!decoded) return null;
    const node = urlObj.searchParams.get("node") || "direct";
    return { target: new URL(decoded), node };
  } catch (_) {
    return null;
  }
}

async function clientContext(clientId) {
  if (!clientId) return { target: null, node: "direct" };
  try {
    const client = await self.clients.get(clientId);
    if (!client) return { target: null, node: "direct" };
    const cu = new URL(client.url);
    const parsed = parseProxyUrl(cu);
    if (parsed) return parsed;
    return { target: null, node: "direct" };
  } catch (_) {
    return { target: null, node: "direct" };
  }
}

async function tunnel(req, targetUrl, node) {
  const endpoint = `${PROXY_ENDPOINT}?url=${b64urlEncode(targetUrl)}&node=${encodeURIComponent(node)}`;

  try {
    const hasBody = req.method !== "GET" && req.method !== "HEAD";
    let body;
    if (hasBody) {
      const cl = parseInt(req.headers.get("content-length") || "0", 10);
      if (cl > MAX_SW_BODY_BYTES) {
        console.warn("[GhostGrid SW] body too large to buffer, bypassing:", targetUrl, cl);
        return fetch(req);
      }
      body = await req.arrayBuffer();
    }
    return await fetch(endpoint, {
      method: req.method,
      headers: req.headers,
      body,
      credentials: "same-origin",
    });
  } catch (err) {
    console.warn("[GhostGrid SW] tunnel failed:", targetUrl, err);
    return new Response("GhostGrid tunnel error", {
      status: 502,
      headers: { "Content-Type": "text/plain" },
    });
  }
}

self.addEventListener("fetch", (event) => {
  const req = event.request;

  let url;
  try {
    url = new URL(req.url);
  } catch (_) {
    return;
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return;

  if (url.origin === self.location.origin && SELF_PREFIXES.some((p) => url.pathname.startsWith(p))) {
    return;
  }

  const alreadyProxied = parseProxyUrl(url);
  if (alreadyProxied && url.origin === self.location.origin) {
    return;
  }

  if (alreadyProxied) {
    event.respondWith(tunnel(req, alreadyProxied.target.href, alreadyProxied.node));
    return;
  }

  if (url.origin !== self.location.origin) {
    event.respondWith((async () => {
      const ctx = await clientContext(event.clientId);
      return tunnel(req, req.url, ctx.node || "direct");
    })());
    return;
  }

  if (req.mode === "navigate") return;

  event.respondWith((async () => {
    const ctx = await clientContext(event.clientId);
    if (!ctx.target) {
      return new Response("GhostGrid: no client context for remap", {
        status: 502,
        headers: { "Content-Type": "text/plain" },
      });
    }
    const remapped = new URL(url.pathname + url.search, ctx.target.origin).href;
    return tunnel(req, remapped, ctx.node || "direct");
  })());
});