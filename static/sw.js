/**
 * GhostGrid Client-Side Service Worker Engine
 * Intercepts background asset calls, video chunk streams, and dynamic scripts.
 */

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

function encodeUrl(url) {
  const utf8 = new TextEncoder().encode(url);
  let binary = "";
  utf8.forEach((b) => (binary += String.fromCharCode(b)));
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

self.addEventListener("fetch", (event) => {
  const reqUrl = event.request.url;

  // Let local GhostGrid assets, APIs, and endpoints pass through directly
  if (
    reqUrl.includes("/static/") ||
    reqUrl.includes("/api/") ||
    reqUrl.includes("/proxy/") ||
    reqUrl.includes("/browser") ||
    reqUrl.endsWith("/sw.js")
  ) {
    return;
  }

  // Intercept any outgoing request and route it through the proxy
  const node = "direct";
  const proxiedEndpoint = `/proxy/fetch?url=${encodeUrl(reqUrl)}&node=${node}`;

  event.respondWith(
    fetch(proxiedEndpoint, {
      method: event.request.method,
      headers: event.request.headers,
      body: event.request.method !== "GET" && event.request.method !== "HEAD" ? event.request.body : undefined,
    }).catch(() => {
      return new Response("", { status: 204 });
    })
  );
});