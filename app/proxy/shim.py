"""
app/proxy/shim.py

Builds the <base> tag + runtime shim that is injected into proxied HTML.

Layer responsibilities (per GhostGrid design):
  - Backend rewriter (html_rewriter.py) handles static <a>/<form>/<img>/<script>...
  - This shim handles DYNAMIC navigation the rewriter cannot see:
      * clicks on links created by JS after page load
      * POST form submissions (native browser submits don't re-enter route)
      * fetch() / XHR initiated by in-page JS
      * window.open()
      * history.pushState/replaceState
  - Service worker handles SUBRESOURCE fetches the shim misses.

This shim MUST be idempotent with the backend rewriter: if an attribute
already points at /proxy/fetch?url=..., the shim must not wrap it again.
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
  var PROXY_PATH = "/proxy/fetch";
  console.log("[GhostGrid] shim active for", TARGET);

  // ---- base64url encode (matches backend url_encoder.encode_url) ----
  function enc(u) {
    var bytes = new TextEncoder().encode(u), bin = "";
    for (var i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function toProxy(abs) {
    return location.origin + PROXY_PATH + "?url=" + enc(abs) + "&node=" + encodeURIComponent(NODE);
  }

  // Was this URL already proxied (by the backend rewriter, a previous shim run,
  // or the service worker)? Returns the already-proxied form if so, else null.
  function alreadyProxied(url) {
    try {
      var u = new URL(url, location.origin);
      if (u.pathname === PROXY_PATH) return u.href;
    } catch (e) {}
    return null;
  }

  function isHttp(url) {
    return url.protocol === "http:" || url.protocol === "https:";
  }

  // Resolve a possibly-relative URL against the upstream TARGET, and wrap it.
  // If already proxied, return as-is.
  function localize(input) {
    if (input === undefined || input === null || input === "") return input;
    var s = String(input);
    var prior = alreadyProxied(s);
    if (prior) return prior;
    var abs;
    try { abs = new URL(s, TARGET); } catch (e) { return input; }
    if (!isHttp(abs)) return input;
    return toProxy(abs.href);
  }

  // ---------------------------------------------------------------- history
  var histProto = window.History && window.History.prototype;
  if (histProto) {
    ["pushState", "replaceState"].forEach(function (name) {
      var orig = histProto[name];
      histProto[name] = function (state, unused, url) {
        try {
          return orig.call(this, state, unused, localize(url));
        } catch (e) {
          try { return orig.call(this, state, unused); } catch (e2) { return undefined; }
        }
      };
    });
  }

  // ---------------------------------------------------------------- fetch()
  // Rewrite cross-origin fetch() URLs so they tunnel through GhostGrid.
  // Same-origin (GhostGrid) URLs are left untouched.
  var origFetch = window.fetch;
  if (origFetch) {
    window.fetch = function (input, init) {
      try {
        if (typeof input === "string" || input instanceof URL) {
          var prior = alreadyProxied(input);
          if (!prior) {
            var abs = new URL(String(input), TARGET);
            if (isHttp(abs) && abs.origin !== location.origin) {
              input = toProxy(abs.href);
            }
          } else {
            input = prior;
          }
        } else if (input && input.url) {
          // Request object — rebuild with proxied URL if needed
          var priorReq = alreadyProxied(input.url);
          if (!priorReq) {
            var absReq = new URL(input.url, TARGET);
            if (isHttp(absReq) && absReq.origin !== location.origin) {
              input = new Request(toProxy(absReq.href), input);
            }
          }
        }
      } catch (e) { /* fall through to original */ }
      return origFetch.call(this, input, init);
    };
  }

  // ---------------------------------------------------------------- XHR
  var origXhrOpen = window.XMLHttpRequest && window.XMLHttpRequest.prototype.open;
  if (origXhrOpen) {
    window.XMLHttpRequest.prototype.open = function (method, url) {
      try {
        if (typeof url === "string") {
          var prior = alreadyProxied(url);
          if (prior) {
            url = prior;
          } else {
            var abs = new URL(url, TARGET);
            if (isHttp(abs) && abs.origin !== location.origin) {
              url = toProxy(abs.href);
            }
          }
        }
      } catch (e) { /* fall through */ }
      return origXhrOpen.apply(this, argumentsWithUrl(this, arguments, url));
    };
    function argumentsWithUrl(ctx, args, url) {
      var a = Array.prototype.slice.call(args);
      a[1] = url;
      return a;
    }
  }

  // ---------------------------------------------------------------- clicks
  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target && e.target.closest ? e.target.closest("a[href]") : null;
    if (!a || a.hasAttribute("download")) return;
    var rawHref = a.getAttribute("href");
    if (!rawHref) return;

    // Anchor-only: scroll in-document, don't navigate.
    if (rawHref.charAt(0) === "#") {
      try {
        var el = document.getElementById(decodeURIComponent(rawHref.slice(1)));
        if (el) { e.preventDefault(); el.scrollIntoView(); }
      } catch (err) {}
      return;
    }

    // Already proxied (by backend rewriter): let the browser follow normally.
    var prior = alreadyProxied(rawHref);
    if (prior) {
      // For target=_blank, browser will open in new tab naturally. Nothing to do.
      return;
    }

    var abs;
    try { abs = new URL(rawHref, TARGET); } catch (err) { return; }
    if (!isHttp(abs)) return;

    // Same-document fragment on the same upstream page: scroll, don't navigate.
    if (abs.hash && abs.href.split("#")[0] === TARGET.split("#")[0]) {
      try {
        var el2 = document.getElementById(decodeURIComponent(abs.hash.slice(1)));
        if (el2) { e.preventDefault(); el2.scrollIntoView(); return; }
      } catch (err2) {}
    }

    e.preventDefault();
    var proxied = toProxy(abs.href);
    if (a.target === "_blank") {
      window.open(proxied, "_blank", "noopener");
    } else {
      location.assign(proxied);
    }
  }, true);  // capture phase — beats framework click handlers that might stopPropagation

  // ---------------------------------------------------------------- forms
  document.addEventListener("submit", function (e) {
    var f = e.target;
    if (e.defaultPrevented || !f || f.tagName !== "FORM") return;

    // If the backend rewriter already wrapped action, don't touch it.
    var rawAction = f.getAttribute("action") || TARGET;
    if (alreadyProxied(rawAction)) return;

    // Preserve the true original action across submissions.
    if (!f.dataset.ghostgridOriginalAction) {
      f.dataset.ghostgridOriginalAction = rawAction;
    }
    var effectiveAction = f.dataset.ghostgridOriginalAction;

    var method = (f.getAttribute("method") || "get").toLowerCase();
    var action;
    try { action = new URL(effectiveAction, TARGET); } catch (err) { return; }
    if (!isHttp(action)) return;

    if (method === "get") {
      // Preserve any query params already on the action URL.
      new FormData(f).forEach(function (v, k) {
        if (typeof v === "string") action.searchParams.append(k, v);
      });
      e.preventDefault();
      location.assign(toProxy(action.href));
    } else {
      // POST/PUT/PATCH: mutate action so the native submission routes through us.
      // We store the original in dataset so re-submits compute the right URL.
      f.setAttribute("action", toProxy(action.href));
    }
  }, true);

  // ---------------------------------------------------------------- window.open
  var origOpen = window.open;
  window.open = function (u, t, ftr) {
    if (u) {
      try {
        var prior = alreadyProxied(String(u));
        if (prior) {
          u = prior;
        } else {
          var a = new URL(String(u), TARGET);
          if (isHttp(a)) u = toProxy(a.href);
        }
      } catch (e) {}
    }
    return origOpen.call(this, u, t, ftr);
  };

  // ---------------------------------------------------------------- Presentation stub
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
    return json.dumps(value).replace("<", "\\u003c")


def build_shim(final_url: str, node: str) -> str:
    return _SHIM_TEMPLATE.replace("__TARGET__", _js_string(final_url)).replace(
        "__NODE__", _js_string(node)
    )


def inject_into_html(html_text: str, final_url: str, node: str = "direct") -> str:
    injection = f'<base href="{escape(final_url, quote=True)}">\n{build_shim(final_url, node)}'

    if _HEAD_RE.search(html_text):
        return _HEAD_RE.sub(lambda m: m.group(0) + injection, html_text, count=1)
    if _HTML_RE.search(html_text):
        return _HTML_RE.sub(
            lambda m: m.group(0) + "<head>" + injection + "</head>", html_text, count=1
        )
    return injection + html_text