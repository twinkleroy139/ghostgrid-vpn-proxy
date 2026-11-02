/**
 * GhostGrid Client-Side Service Worker (v3)
 */

const PROXY_ENDPOINT = "/proxy/fetch";

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
    event.respondWith(tunnel(event, req, req.url));
    return;
  }

  // Same-origin
  if (req.mode === "navigate") return;
  if (LOCAL_PREFIXES.some((p) => url.pathname.startsWith(p))) return;

  event.respondWith(handleSameOrigin(event, req, url));
});

// Extract target URL and Node from the client's URL
async function clientContext(clientId) {
  if (!clientId) return { target: null, node: "direct" };
  try {
    const client = await self.clients.get(clientId);
    if (!client) return { target: null, node: "direct" };
    const cu = new URL(client.url);
    if (cu.origin !== self.location.origin || cu.pathname !== PROXY_ENDPOINT) return { target: null, node: "direct" };
    
    const token = cu.searchParams.get("url");
    const node = cu.searchParams.get("node") || "direct"; // Dynamically grab the node
    const decoded = token ? decodeToken(token) : null;
    
    return { 
        target: decoded ? new URL(decoded) : null,
        node: node 
    };
  } catch (_) {
    return { target: null, node: "direct" };
  }
}

async function handleSameOrigin(event, req, url) {
  const context = await clientContext(event.clientId);
  if (!context.target) return fetch(req);
  const remapped = new URL(url.pathname + url.search, context.target.origin).href;
  return tunnel(event, req, remapped, context.node);
}

async function tunnel(event, req, targetUrl, overrideNode = null) {
  // If no override node provided, look it up from the client context
  let activeNode = overrideNode;
  if (!activeNode) {
      const context = await clientContext(event.clientId);
      activeNode = context.node;
  }

  const endpoint = `${PROXY_ENDPOINT}?url=${encodeUrl(targetUrl)}&node=${activeNode}`;
  try {
    const hasBody = req.method !== "GET" && req.method !== "HEAD";
    const body = hasBody ? await req.arrayBuffer() : undefined; 
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