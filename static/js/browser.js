/**
 * GhostGrid Browser Workspace Controller
 * Handles URL encoding, VPN node routing, and iframe lifecycle.
 */

function encodeTargetUrl(url) {
  if (!url) return "";
  const cleanUrl = url.trim();
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
  const vpnNodeSelect = document.getElementById("vpnNodeSelect");

  // Load and populate available nodes from backend
  async function loadVpnNodes() {
    try {
      const res = await fetch("/proxy/nodes");
      if (res.ok) {
        const data = await res.json();
        vpnNodeSelect.innerHTML = "";
        data.nodes.forEach((n) => {
          const opt = document.createElement("option");
          opt.value = n.id;
          opt.textContent = n.name + (n.configured ? "" : " [UNCONFIGURED]");
          vpnNodeSelect.appendChild(opt);
        });
        const savedNode = localStorage.getItem("ghostgrid_vpn_node") || "direct";
        vpnNodeSelect.value = savedNode;
      }
    } catch (e) {
      console.warn("Could not load dynamic nodes, using defaults.");
    }
  }

  vpnNodeSelect.addEventListener("change", () => {
    localStorage.setItem("ghostgrid_vpn_node", vpnNodeSelect.value);
  });

  function navigateTo(url) {
    if (!url) return;
    const token = encodeTargetUrl(url);
    if (!token) return;

    const selectedNode = vpnNodeSelect ? vpnNodeSelect.value : "direct";

    if (frameLoader) frameLoader.style.display = "block";
    if (activeUrlDisplay) activeUrlDisplay.textContent = `${url} [${selectedNode.toUpperCase()}]`;

    // Load through GhostGrid proxy endpoint with node indicator
    proxyFrame.src = `/proxy/fetch?url=${token}&node=${encodeURIComponent(selectedNode)}`;
  }

  if (launchBtn && urlInput) {
    launchBtn.addEventListener("click", () => navigateTo(urlInput.value));
    urlInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        navigateTo(urlInput.value);
      }
    });
  }

  if (reloadBtn && proxyFrame) {
    reloadBtn.addEventListener("click", () => {
      if (proxyFrame.src && proxyFrame.src !== "about:blank") {
        if (frameLoader) frameLoader.style.display = "block";
        proxyFrame.src = proxyFrame.src;
      }
    });
  }

  if (proxyFrame) {
    proxyFrame.addEventListener("load", () => {
      if (frameLoader) frameLoader.style.display = "none";
    });
  }

  loadVpnNodes().then(() => {
    const params = new URLSearchParams(window.location.search);
    const initialTarget = params.get("q");
    if (initialTarget && urlInput) {
      urlInput.value = initialTarget;
      navigateTo(initialTarget);
    }
  });
});