/**
 * GhostGrid Client-Side Service Worker (v2)
 *
 * Tunnels every cross-origin request made by a proxied page through
 * /proxy/fetch. GhostGrid's own origin (pages, /static, /api, /proxy)
 * passes through untouched.
 *
 * NOTE: navigations (link clicks, nested iframes, location changes) are NOT
 * seen by this worker, because navigation requests are routed to the SW whose
 * scope matches the destination. The injected page shim handles those.
 */

const PROXY_ENDPOINT = "/proxy/fetch";
const NODE = "direct"; // TODO: SW cannot read localStorage; pass node via postMessage later

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

function encodeUrl(url) {
  const utf8 = new TextEncoder().encode(url);
  let binary = "";
  utf8.forEach((b) => (binary += String.fromCharCode(b)));
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
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

  // Origin check (not substring matching): only GhostGrid itself is exempt.
  if (url.origin === self.location.origin) return;

  event.respondWith(tunnel(req));
});

async function tunnel(req) {
  const endpoint = `${PROXY_ENDPOINT}?url=${encodeUrl(req.url)}&node=${NODE}`;
  try {
    const hasBody = req.method !== "GET" && req.method !== "HEAD";
    // Buffer the body: forwarding a ReadableStream requires `duplex: "half"`
    const body = hasBody ? await req.arrayBuffer() : undefined;

    return await fetch(endpoint, {
      method: req.method,
      headers: req.headers,
      body,
      credentials: "same-origin",
    });
  } catch (err) {
    console.warn("[GhostGrid SW] tunnel failed:", req.url, err);
    // 502 (not 204) so failures are visible in DevTools while debugging
    return new Response("GhostGrid tunnel error", {
      status: 502,
      headers: { "Content-Type": "text/plain" },
    });
  }
}