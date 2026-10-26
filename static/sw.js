/**
 * GhostGrid Client-Side Service Worker Engine
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
    reqUrl.endsWith("/sw.js") ||
    reqUrl.endsWith("/favicon.ico")
  ) {
    return;
  }

  const node = "direct";
  const proxiedEndpoint = `/proxy/fetch?url=${encodeUrl(reqUrl)}&node=${node}`;

  event.respondWith(
    fetch(proxiedEndpoint, {
      method: event.request.method,
      headers: event.request.headers,
      body: event.request.method !== "GET" && event.request.method !== "HEAD" ? event.request.body : undefined,
    }).catch(() => {
      // Must pass null body when returning status 204
      return new Response(null, { status: 204 });
    })
  );
});