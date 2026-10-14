/**
 * GhostGrid Browser Workspace Controller
 * Handles URL encoding, target site launching, iframe history, and navigation controls.
 */

// URL-safe Base64 encoder matching Python backend url_encoder.py
function encodeTargetUrl(url) {
  if (!url) return "";
  const cleanUrl = url.trim();
  // Ensure protocol is attached if user enters bare domain
  const finalUrl = /^https?:\/\//i.test(cleanUrl) ? cleanUrl : `https://${cleanUrl}`;
  const utf8Bytes = new TextEncoder().encode(finalUrl);
  let binary = "";
  utf8Bytes.forEach((b) => (binary += String.fromCharCode(b)));
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

document.addEventListener("DOMContentLoaded", () => {
  const urlInput = document.getElementById("targetUrlInput");
  const launchBtn = document.getElementById("launchBtn");
  const reloadBtn = document.getElementById("reloadBtn");
  const proxyFrame = document.getElementById("proxyFrame");
  const frameLoader = document.getElementById("frameLoader");
  const activeUrlDisplay = document.getElementById("activeUrlDisplay");

  function navigateTo(url) {
    if (!url) return;
    const token = encodeTargetUrl(url);
    if (!token) return;

    if (frameLoader) frameLoader.style.display = "block";
    if (activeUrlDisplay) activeUrlDisplay.textContent = url;

    // Load target through GhostGrid proxy endpoint
    proxyFrame.src = `/proxy/fetch?url=${token}`;
  }

  // Handle URL form submit / enter key
  if (launchBtn && urlInput) {
    launchBtn.addEventListener("click", () => navigateTo(urlInput.value));
    urlInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        navigateTo(urlInput.value);
      }
    });
  }

  // Reload current iframe
  if (reloadBtn && proxyFrame) {
    reloadBtn.addEventListener("click", () => {
      if (proxyFrame.src && proxyFrame.src !== "about:blank") {
        if (frameLoader) frameLoader.style.display = "block";
        proxyFrame.src = proxyFrame.src;
      }
    });
  }

  // Hide loader indicator once iframe content finishes rendering
  if (proxyFrame) {
    proxyFrame.addEventListener("load", () => {
      if (frameLoader) frameLoader.style.display = "none";
    });
  }

  // Check URL params for direct launch e.g. /browser?q=example.com
  const params = new URLSearchParams(window.location.search);
  const initialTarget = params.get("q");
  if (initialTarget && urlInput) {
    urlInput.value = initialTarget;
    navigateTo(initialTarget);
  }
});