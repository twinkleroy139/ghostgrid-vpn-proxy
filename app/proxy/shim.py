"""
app/proxy/shim.py
 
Builds the <base> tag + runtime shim that is injected into proxied HTML.
 
The shim:
  * patches History.prototype so cross-origin replaceState/pushState never throws
  * wraps fetch() so mode:"same-origin" is downgraded to "cors" (SW then tunnels it)
  * intercepts link clicks, GET form submits and window.open, because
    navigations never reach the service worker
"""
 
import json
import re
from html import escape
 
_HEAD_RE = re.compile(r"<head(?=[\s>])[^>]*>", re.IGNORECASE)
_HTML_RE = re.compile(r"<html(?=[\s>])[^>]*>", re.IGNORECASE)
 
_SHIM_TEMPLATE = r"""
<script id="ghostgrid-runtime-shim">
(function () {
  "use strict";
  var TARGET = __TARGET__;
  var NODE = __NODE__;
 
  function enc(u) {
    var bytes = new TextEncoder().encode(u), bin = "";
    for (var i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  function toProxy(abs) {
    return location.origin + "/proxy/fetch?url=" + enc(abs) + "&node=" + encodeURIComponent(NODE);
  }
 
  // 1. History: resolve URLs against GhostGrid's origin, never the <base> origin
  function localize(u) {
    if (u === undefined || u === null || u === "") return u;
    var abs;
    try { abs = new URL(String(u), TARGET); } catch (e) { return undefined; }
    if (abs.pathname === "/proxy/fetch") {
      // page echoed our own location back to us
      return location.origin + abs.pathname + abs.search + abs.hash;
    }
    return toProxy(abs.href);
  }
  var proto = window.History && window.History.prototype;
  if (proto) {
    ["pushState", "replaceState"].forEach(function (name) {
      var orig = proto[name];
      proto[name] = function (state, unused, url) {
        try {
          return orig.call(this, state, unused, localize(url));
        } catch (e) {
          try { return orig.call(this, state, unused); } catch (e2) { return undefined; }
        }
      };
    });
  }
 
  // 2. fetch(): same-origin mode can never work cross-origin inside the proxy
  var origFetch = window.fetch;
  if (origFetch) {
    window.fetch = function (input, init) {
      var mode = (init && init.mode) || (input && input.mode);
      if (mode === "same-origin") {
        init = Object.assign({}, init || {}, { mode: "cors" });
      }
      return origFetch.call(this, input, init);
    };
  }
 
  // 3. Navigations never reach the service worker, so route them ourselves
  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target && e.target.closest ? e.target.closest("a[href]") : null;
    if (!a || a.hasAttribute("download")) return;
    var href;
    try { href = new URL(a.getAttribute("href"), TARGET); } catch (err) { return; }
    if (href.protocol !== "http:" && href.protocol !== "https:") return;
    e.preventDefault();
    if (href.hash && href.href.split("#")[0] === TARGET.split("#")[0]) {
      try {
        var el = document.getElementById(decodeURIComponent(href.hash.slice(1)));
        if (el) el.scrollIntoView();
      } catch (err2) {}
      return;
    }
    location.assign(toProxy(href.href));
  }, false);
 
  document.addEventListener("submit", function (e) {
    var f = e.target;
    if (e.defaultPrevented || !f || f.tagName !== "FORM") return;
    if ((f.getAttribute("method") || "get").toLowerCase() !== "get") return; // POST forms: not handled yet
    var action;
    try { action = new URL(f.getAttribute("action") || TARGET, TARGET); } catch (err) { return; }
    action.search = "";
    new FormData(f).forEach(function (v, k) {
      if (typeof v === "string") action.searchParams.append(k, v);
    });
    e.preventDefault();
    location.assign(toProxy(action.href));
  }, false);
 
  var origOpen = window.open;
  window.open = function (u, t, f) {
    if (u) {
      try {
        var a = new URL(String(u), TARGET);
        if (a.protocol === "http:" || a.protocol === "https:") u = toProxy(a.href);
      } catch (e) {}
    }
    return origOpen.call(this, u, t, f);
  };
 
  // 4. Presentation API stub (only if the sandbox still lacks it)
  if (typeof window.PresentationRequest === "undefined") {
    window.PresentationRequest = function () {
      return {
        start: function () { return Promise.reject(new Error("Presentation disabled")); },
        reconnect: function () { return Promise.reject(new Error("Presentation disabled")); },
        addEventListener: function () {}
      };
    };
  }
})();
</script>
"""
 
 
def _js_string(value: str) -> str:
    # json.dumps gives a valid JS string literal; escape "<" so "</script>" can't break out
    return json.dumps(value).replace("<", "\\u003c")
 
 
def build_shim(final_url: str, node: str) -> str:
    return _SHIM_TEMPLATE.replace("__TARGET__", _js_string(final_url)).replace(
        "__NODE__", _js_string(node)
    )
 
 
def inject_into_html(html_text: str, final_url: str, node: str = "direct") -> str:
    """Insert <base> + shim as the very first things inside <head>."""
    injection = f'<base href="{escape(final_url, quote=True)}">\n{build_shim(final_url, node)}'
 
    if _HEAD_RE.search(html_text):
        return _HEAD_RE.sub(lambda m: m.group(0) + injection, html_text, count=1)
    if _HTML_RE.search(html_text):
        return _HTML_RE.sub(lambda m: m.group(0) + "<head>" + injection + "</head>", html_text, count=1)
    return injection + html_text