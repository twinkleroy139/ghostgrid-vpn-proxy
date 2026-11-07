/**
 * GhostGrid Browser Workspace Controller
 * Handles URL encoding, VPN node routing, iframe lifecycle,
 * the CONNECT/DISCONNECT button + live VPN status,
 * and WAF-blocked page detection with an escape hatch.
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

function formatUptime(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0));
  const hh = String(Math.floor(s / 3600)).padStart(2, "0");
  const mm = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
  const ss = String(s % 60).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

document.addEventListener("DOMContentLoaded", () => {

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker
      .register("/sw.js", { scope: "/" })
      .then((reg) => console.log("[GhostGrid] SW Registered with scope:", reg.scope))
      .catch((err) => console.warn("[GhostGrid] SW Registration failed:", err));
  }

  const urlInput = document.getElementById("targetUrlInput");
  const launchBtn = document.getElementById("launchBtn");
  const reloadBtn = document.getElementById("reloadBtn");
  const proxyFrame = document.getElementById("proxyFrame");
  const frameLoader = document.getElementById("frameLoader");
  const activeUrlDisplay = document.getElementById("activeUrlDisplay");
  const vpnNodeSelect = document.getElementById("vpnNodeSelect");

  const vpnStatusDot = document.getElementById("vpnStatusDot");
  const vpnStatusText = document.getElementById("vpnStatusText");
  const vpnEgressIp = document.getElementById("vpnEgressIp");
  const connectBtn = document.getElementById("connectBtn");

  const wafBanner = document.getElementById("wafBanner");
  const wafBannerText = document.getElementById("wafBannerText");
  const wafEscapeLink = document.getElementById("wafEscapeLink");

  // ---------------------------------------------------------- UI STATE
  const NODE_IPS = {};
  let lastStatus = { connected: false, node: "direct", degraded: false, uptime_seconds: 0 };
  let pollHandle = null;
  let tickHandle = null;
  let connectedAtMs = 0;
  let lastNode = "direct";
  let connectInProgress = false;
  let currentTargetUrl = "";

  function setStatusDot(color, glow) {
    vpnStatusDot.style.background = color;
    vpnStatusDot.style.boxShadow = `0 0 8px ${glow || color}`;
  }

  function applyUiState(status) {
    lastStatus = status;
    const node = status.node || "direct";
    const isDirect = node === "direct";
    const isConnected = !!status.connected;
    const isDegraded = !!status.degraded;

    if (isConnected) {
      const uptime = status.uptime_seconds || 0;
      vpnStatusText.textContent = `CONNECTED ${formatUptime(uptime)}`;
      setStatusDot(isDegraded ? "#ffaa00" : "#00ff88");
    } else if (connectInProgress) {
      vpnStatusText.textContent = "CONNECTING...";
      setStatusDot("#ffcc00");
    } else if (isDirect) {
      vpnStatusText.textContent = "DIRECT";
      setStatusDot("var(--neon-cyan)");
    } else {
      vpnStatusText.textContent = "DISCONNECTED";
      setStatusDot("var(--text-muted)");
    }

    if (isDirect && !connectInProgress) {
      connectBtn.style.display = "none";
    } else if (isConnected) {
      connectBtn.style.display = "inline-block";
      connectBtn.textContent = "DISCONNECT";
      connectBtn.disabled = false;
      connectBtn.classList.add("cyber-btn-magenta");
    } else if (connectInProgress) {
      connectBtn.style.display = "inline-block";
      connectBtn.textContent = "CONNECTING...";
      connectBtn.disabled = true;
      connectBtn.classList.remove("cyber-btn-magenta");
    } else {
      connectBtn.style.display = "inline-block";
      connectBtn.textContent = "CONNECT";
      connectBtn.disabled = false;
      connectBtn.classList.remove("cyber-btn-magenta");
    }

    if (NODE_IPS[node]) {
      vpnEgressIp.textContent = NODE_IPS[node];
      vpnEgressIp.style.opacity = "0.9";
    } else if (isDirect) {
      vpnEgressIp.textContent = "—";
      vpnEgressIp.style.opacity = "0.5";
    } else {
      vpnEgressIp.textContent = isConnected ? "resolving…" : "—";
      vpnEgressIp.style.opacity = "0.5";
    }
  }

  function startTick() {
    if (tickHandle) clearInterval(tickHandle);
    tickHandle = setInterval(() => {
      if (lastStatus.connected && connectedAtMs > 0) {
        const elapsed = Math.floor((Date.now() - connectedAtMs) / 1000);
        vpnStatusText.textContent = `CONNECTED ${formatUptime(elapsed)}`;
      }
    }, 1000);
  }

  // ---------------------------------------------------------- WAF BANNER
  function showWafBanner(realUrl) {
    if (!realUrl) {
      wafBanner.style.display = "none";
      return;
    }
    wafBannerText.textContent = `This site is protected by WAF bot detection and cannot be proxied. Open it directly in a new tab instead.`;
    wafEscapeLink.href = realUrl;
    wafBanner.style.display = "flex";
  }

  function hideWafBanner() {
    wafBanner.style.display = "none";
    wafEscapeLink.href = "#";
  }

  // ---------------------------------------------------------- STATUS POLLING
  async function pollStatus() {
    try {
      const res = await fetch("/proxy/status");
      if (!res.ok) return;
      const status = await res.json();

      if (status.connected && status.uptime_seconds > 0) {
        connectedAtMs = Date.now() - status.uptime_seconds * 1000;
      }

      if (status.connected && !NODE_IPS[status.node]) {
        fetchEgressIp(status.node);
      }

      applyUiState(status);
    } catch (e) {}
  }

  function schedulePoll() {
    if (pollHandle) clearTimeout(pollHandle);
    const interval = lastStatus.connected ? 2000 : 5000;
    pollHandle = setTimeout(async () => {
      await pollStatus();
      schedulePoll();
    }, interval);
  }

  // ---------------------------------------------------------- EGRESS IP
  async function fetchEgressIp(node) {
    try {
      const token = encodeTargetUrl("https://api.ipify.org");
      const res = await fetch(`/proxy/fetch?url=${token}&node=${encodeURIComponent(node)}`);
      if (!res.ok) return;
      const text = (await res.text()).trim();
      if (/^\d{1,3}(\.\d{1,3}){3}$/.test(text)) {
        NODE_IPS[node] = text;
        if (lastStatus.node === node) {
          vpnEgressIp.textContent = text;
          vpnEgressIp.style.opacity = "0.9";
        }
      }
    } catch (e) {}
  }

  // ---------------------------------------------------------- CONNECT / DISCONNECT
  async function connectVpn(node) {
    connectInProgress = true;
    applyUiState({ connected: false, node, degraded: false, uptime_seconds: 0 });

    try {
      const res = await fetch(`/proxy/connect?node=${encodeURIComponent(node)}`, {
        method: "POST",
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "VPN connect failed");
      }
      const status = await res.json();
      connectedAtMs = Date.now() - (status.uptime_seconds || 0) * 1000;
      connectInProgress = false;
      applyUiState(status);
      startTick();
      fetchEgressIp(node);
    } catch (e) {
      console.warn("[GhostGrid] connect failed:", e);
      connectInProgress = false;
      setStatusDot("#ff3355");
      vpnStatusText.textContent = "ERROR";
      vpnEgressIp.textContent = "—";
      setTimeout(() => applyUiState({ connected: false, node: vpnNodeSelect.value, degraded: false, uptime_seconds: 0 }), 2000);
    }
  }

  async function disconnectVpn() {
    try {
      const res = await fetch("/proxy/disconnect", { method: "POST" });
      if (res.ok) {
        const status = await res.json();
        connectedAtMs = 0;
        applyUiState(status);
        Object.keys(NODE_IPS).forEach((k) => delete NODE_IPS[k]);
        vpnEgressIp.textContent = "—";
      }
    } catch (e) {
      console.warn("[GhostGrid] disconnect failed:", e);
    }
  }

  connectBtn.addEventListener("click", async () => {
    if (connectInProgress) return;
    if (lastStatus.connected) {
      await disconnectVpn();
    } else {
      const node = vpnNodeSelect.value;
      if (node === "direct") return;
      await connectVpn(node);
    }
  });

  // ---------------------------------------------------------- NODE SELECT
  async function loadVpnNodes() {
    try {
      const res = await fetch("/proxy/nodes");
      if (res.ok) {
        const data = await res.json();
        vpnNodeSelect.innerHTML = "";
        data.nodes.forEach((n) => {
          const opt = document.createElement("option");
          opt.value = n.id;
          const suffix = n.configured ? "" : " [UNCONFIGURED]";
          opt.textContent = n.name + suffix;
          if (!n.configured) {
            opt.disabled = true;
            opt.style.opacity = "0.5";
          }
          vpnNodeSelect.appendChild(opt);
        });
        const savedNode = localStorage.getItem("ghostgrid_vpn_node") || "direct";
        vpnNodeSelect.value = savedNode;
        lastNode = savedNode;
        applyUiState({ connected: false, node: savedNode, degraded: false, uptime_seconds: 0 });
      }
    } catch (e) {
      console.warn("Could not load dynamic nodes, using defaults.");
    }
  }

  vpnNodeSelect.addEventListener("change", async () => {
    const newValue = vpnNodeSelect.value;
    if (lastStatus.connected && lastStatus.node !== newValue) {
      await disconnectVpn();
    }
    lastNode = newValue;
    localStorage.setItem("ghostgrid_vpn_node", newValue);
    applyUiState({ connected: false, node: newValue, degraded: false, uptime_seconds: 0 });
  });

  // ---------------------------------------------------------- NAVIGATION
  function normalizeUrl(url) {
    if (!url) return "";
    const u = url.trim();
    return /^https?:\/\//i.test(u) ? u : `https://${u}`;
  }

  function navigateTo(url) {
    if (!url) return;
    const target = normalizeUrl(url);
    const token = encodeTargetUrl(target);
    if (!token) return;

    const selectedNode = vpnNodeSelect ? vpnNodeSelect.value : "direct";

    currentTargetUrl = target;
    if (frameLoader) frameLoader.style.display = "block";
    if (activeUrlDisplay) activeUrlDisplay.textContent = `${target} [${selectedNode.toUpperCase()}]`;
    hideWafBanner();

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
        hideWafBanner();
        proxyFrame.src = proxyFrame.src;
      }
    });
  }

  if (proxyFrame) {
    proxyFrame.addEventListener("load", () => {
      if (frameLoader) frameLoader.style.display = "none";

      // Detect WAF SHIELD error page inside the iframe and offer escape hatch.
      // Same-origin (both are ghostgrid-proxy.onrender.com), so we can read the body.
      try {
        const doc = proxyFrame.contentDocument || proxyFrame.contentWindow.document;
        if (!doc) return;
        const bodyText = doc.body ? doc.body.innerText || "" : "";
        const titleText = doc.title || "";
        const isWafPage =
          bodyText.includes("WAF SHIELD") ||
          titleText.includes("Terminal Fault");
        if (isWafPage && currentTargetUrl) {
          showWafBanner(currentTargetUrl);
        } else {
          hideWafBanner();
        }
      } catch (e) {
        // Cross-origin or sandboxed — ignore
      }
    });
  }

  // ---------------------------------------------------------- BOOT
  loadVpnNodes().then(async () => {
    await pollStatus();
    schedulePoll();

    const params = new URLSearchParams(window.location.search);
    const initialTarget = params.get("q");
    if (initialTarget && urlInput) {
      urlInput.value = initialTarget;
      navigateTo(initialTarget);
    }
  });
});