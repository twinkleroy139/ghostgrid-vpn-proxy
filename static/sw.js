/**
 * GhostGrid Client-Side Service Worker (v3)
 *
 * 1. Cross-origin requests from proxied pages are tunnelled through /proxy/fetch.
 * 2. Same-origin requests coming FROM a proxied page (e.g. YouTube building URLs
 *    from location.origin) are remapped onto the target site's origin, then tunnelled.
 * 3. GhostGrid's own pages/APIs behave normally.
 *
 * Navigations are never seen here (they are routed by destination scope);
 * the injected page shim handles link clicks / forms.
 */

const PROXY_ENDPOINT = "/proxy/fetch";
const NODE = "direct"; // TODO: SW cannot read localStorage; pass node via postMessage later

// Same-origin paths that always belong to GhostGrid itself
const LOCAL_PREFIXES = ["/proxy/", "/static/", "/sw.js", "/favicon.ico"];

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

function encodeUrl(url) {
  const utf8 = new TextEncoder().encode(url);
  let binary = "";
  utf8.forEach((b) => (binary += String.fromCharCode(b)));
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function decodeToken(token) {
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

self.addEventListener("fetch", (event) => {
  const req = event.request;

  let url;
  try {
    url = new URL(req.url);
  } catch (_) {
    return;
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return;

  // Cross-origin: always tunnel
  if (url.origin !== self.location.origin) {
    event.respondWith(tunnel(req, req.url));
    return;
  }

  // Same-origin
  if (req.mode === "navigate") return;
  if (LOCAL_PREFIXES.some((p) => url.pathname.startsWith(p))) return;

  event.respondWith(handleSameOrigin(event, req, url));
});

// Which site is the requesting page showing? Read it from the client's own URL.
async function targetForClient(clientId) {
  if (!clientId) return null;
  try {
    const client = await self.clients.get(clientId);
    if (!client) return null;
    const cu = new URL(client.url);
    if (cu.origin !== self.location.origin || cu.pathname !== PROXY_ENDPOINT) return null;
    const token = cu.searchParams.get("url");
    const decoded = token ? decodeToken(token) : null;
    return decoded ? new URL(decoded) : null;
  } catch (_) {
    return null;
  }
}

async function handleSameOrigin(event, req, url) {
  const target = await targetForClient(event.clientId);
  if (!target) return fetch(req); // GhostGrid's own page calling its own API
  const remapped = new URL(url.pathname + url.search, target.origin).href;
  return tunnel(req, remapped);
}

async function tunnel(req, targetUrl) {
  const endpoint = `${PROXY_ENDPOINT}?url=${encodeUrl(targetUrl)}&node=${NODE}`;
  try {
    const hasBody = req.method !== "GET" && req.method !== "HEAD";
    const body = hasBody ? await req.arrayBuffer() : undefined; // buffer: streams need duplex
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