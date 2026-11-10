# ⚡ GhostGrid
### Production-Oriented, No-Install Web Proxy & VPN Gateway

<div align="center">

**Browse through a browser-based proxy powered by FastAPI and a userspace WireGuard VPN tunnel.**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![WireGuard](https://img.shields.io/badge/WireGuard-Wireproxy-red.svg)](https://www.wireguard.com/)
[![Deployment](https://img.shields.io/badge/Deployment-Render-black.svg)](https://render.com/)
[![Frontend](https://img.shields.io/badge/Frontend-Vanilla%20JS-yellow.svg)](https://developer.mozilla.org/en-US/docs/Web/JavaScript)

🌐 **Live Demo:** [ghostgrid-proxy.onrender.com](https://ghostgrid-proxy.onrender.com)

</div>

---

## 📖 Overview

**GhostGrid** is a browser-based web proxy and VPN gateway designed to provide access to remote websites without requiring users to install a traditional VPN client or desktop application.

Unlike conventional HTTP proxies that simply forward requests, GhostGrid integrates a userspace **WireGuard VPN tunnel** through Wireproxy and Proton VPN configuration files. Its backend combines FastAPI, asynchronous networking, and browser impersonation to retrieve, process, rewrite, and serve remote web content through a controlled browsing environment.

The platform uses a coordinated backend and frontend architecture to handle modern website resources, navigation, cookies, and proxy routing.

### ✨ Core Features

| Feature | Description |
|---|---|
| **VPN Egress** | Routes supported outbound proxy traffic through a WireGuard tunnel using Wireproxy and Proton VPN configurations |
| **Tunnel Management** | Connect/disconnect controls with tunnel status, uptime, and egress IP information |
| **HTML Rewriting** | Rewrites links, forms, images, scripts, and other resource references to route supported requests through GhostGrid |
| **CSS Rewriting** | Processes CSS `url()` and `@import` references to preserve proxied resource loading |
| **Browser Shim** | Intercepts selected JavaScript navigation, fetch requests, and browser history operations |
| **Service Worker** | Adds a client-side navigation interception layer for supported browsing flows |
| **TLS Impersonation** | Uses `curl_cffi` browser impersonation to improve compatibility with websites that apply basic bot-detection checks |
| **WAF Detection** | Detects selected anti-bot and access-denial responses and provides a graceful fallback experience |
| **Cookie Isolation** | Manages proxied cookies to reduce unwanted interference between browsing sessions |
| **SSRF Protection** | Applies restrictions against private IP ranges, localhost, and cloud metadata endpoints |
| **Restricted Browser Environment** | Displays proxied content inside a sandboxed iframe |

> **Important:** Website compatibility depends on the target website's security controls, JavaScript behavior, authentication requirements, and resource-loading architecture. GhostGrid does not guarantee access to every website.

---

## 🏗️ System Architecture

GhostGrid follows a layered architecture that separates browser interaction, request processing, security validation, and VPN routing.

```text
                   USER BROWSER
                        │
                        ▼
              GhostGrid Web Interface
                  HTML / CSS / JS
                        │
                        ▼
             Browser Compatibility Layer
              ├── JavaScript Shim
              ├── Service Worker
              └── Navigation Interception
                        │
                        ▼
                FastAPI Backend
                        │
          ┌─────────────┼──────────────┐
          ▼             ▼              ▼
     HTML/CSS       Cookie Manager   SSRF Guard
     Rewriters       & Isolation     IP Validation
          │             │              │
          └─────────────┼──────────────┘
                        │
                        ▼
                Async Request Engine
                  curl_cffi / httpx
                        │
                        ▼
                   VPN Manager
                Wireproxy Subprocess
                        │
                        ▼
                 SOCKS5 Interface
                        │
                        ▼
                WireGuard Tunnel
                  Proton VPN
                        │
                        ▼
                 Remote Websites
```

### 🔄 Request Lifecycle

1. **User Input:** The user enters a destination URL in the GhostGrid browser interface.
2. **Request Validation:** The backend validates the destination and applies SSRF protection.
3. **Outbound Routing:** Supported requests are routed through the configured networking path and VPN tunnel.
4. **Remote Fetching:** The asynchronous request engine retrieves the remote response.
5. **Content Processing:** HTML and CSS rewriting adjusts supported resource references and navigation paths.
6. **Response Delivery:** The processed response is returned to the browser interface.
7. **Client-Side Interception:** The JavaScript shim and service worker handle supported navigation and dynamic requests.

---

## 🛠️ Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Backend | Python 3.11+ | Application runtime |
| API Framework | FastAPI | Asynchronous backend and HTTP endpoints |
| ASGI Server | Uvicorn | Application serving |
| HTTP Client | `curl_cffi` | Browser TLS impersonation and HTTP requests |
| Networking | `httpx` | Asynchronous HTTP operations |
| VPN Engine | Wireproxy | Userspace WireGuard networking |
| VPN Provider | Proton VPN | WireGuard configuration and VPN egress |
| HTML Parsing | BeautifulSoup4 | HTML document parsing and rewriting |
| Frontend | HTML5, CSS3, Vanilla JavaScript | Browser interface |
| Authentication | Firebase Admin SDK | Authentication integration |
| Database | Firebase | Application authentication/data integration |
| Deployment | Render | Cloud application hosting |

---

## 🚀 Setup & Installation

### Prerequisites

Before running GhostGrid locally, make sure you have:

- Python 3.11 or newer
- Git
- A Proton VPN account with access to WireGuard configuration files
- A Firebase project for authentication
- Wireproxy binary compatible with your operating system

### 1. Clone the Repository

```bash
git clone https://github.com/twinkleroy139/ghostgrid-vpn-proxy.git
cd ghostgrid-vpn-proxy
```

### 2. Create a Virtual Environment

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root. Use `.env.example` as your reference if available.

```env
ENVIRONMENT=development

SECRET_KEY=replace_with_a_long_random_secret

FIREBASE_CREDENTIALS_JSON={"type":"service_account","project_id":"your-project-id"}
```

**Security note:** The Firebase service account JSON is a private credential. Never commit it to GitHub or expose it through frontend JavaScript.

### 5. Configure the VPN Tunnel

1. Generate or download a WireGuard configuration from Proton VPN.
2. Select a server location supported by your VPN subscription.
3. Save the configuration as:

```text
vpn_configs/
└── proton_us.conf
```

4. Verify that your VPN manager uses the correct configuration path.
5. Keep the WireGuard configuration private.

The example filename represents a US server configuration; the actual egress location depends on the server configuration you provide.

### 6. Start the Application

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open the application:

```text
http://127.0.0.1:8000/browser
```

---

## ☁️ Deployment on Render

GhostGrid can be deployed on [Render](https://render.com/) using its Python application environment or a compatible Docker deployment.

### 1. Connect GitHub Repository

- Push your project to GitHub.
- Create a new Web Service in Render.
- Connect the `ghostgrid-vpn-proxy` repository.
- Select the appropriate runtime and deployment configuration.

### 2. Configure Build & Start Commands

**Build Command**

```bash
pip install -r requirements.txt
```

**Start Command**

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

### 3. Configure Environment Variables

Add the required environment variables through Render's Environment settings.

```env
ENVIRONMENT=production
SECRET_KEY=your_production_secret
FIREBASE_CREDENTIALS_JSON=your_service_account_json
```

Use the actual variable names expected by your application.

### 4. Configure VPN Secret Files

For a deployment that uses Render Secret Files:

- Upload the Proton WireGuard configuration as a secret file.
- Configure the application to read the correct mounted path.
- Example expected path:

```text
/etc/secrets/proton_us.conf
```

Make sure the path matches the implementation in your VPN manager.

### 5. Verify Deployment

After deployment, verify:

- Application health and startup logs.
- Firebase authentication.
- Wireproxy binary availability and execution permissions.
- WireGuard tunnel connectivity.
- SOCKS5 proxy connectivity.
- Actual outbound egress IP.
- HTML rewriting and browser navigation.

> **Deployment consideration:** A successful web-service deployment does not automatically prove that the VPN tunnel is operational. Verify Wireproxy, WireGuard, outbound routing, and the hosting platform's networking restrictions independently.

---

## 🛡️ Security Architecture

Security is a core part of GhostGrid because it fetches content from external websites and handles user browsing requests.

### SSRF Protection

The backend applies destination validation intended to block requests targeting:

- Localhost and loopback addresses.
- Private IPv4 and IPv6 networks.
- Cloud metadata services, including `169.254.169.254`.
- Other restricted internal destinations.

Validation should be performed against resolved IP addresses and repeated after redirects to reduce DNS rebinding and redirect-based SSRF risks.

### Header Sanitization

Request and response headers are processed to reduce unsafe forwarding of host-specific or sensitive headers.

### Cookie Isolation

Cookie handling is designed to isolate remote website sessions from the GhostGrid application environment.

### Browser Sandboxing

Remote website content is displayed inside a restricted iframe environment. Sandbox permissions should be kept as limited as compatibility allows.

### Secret Management

Sensitive configuration should be supplied through environment variables or secret files rather than committed to the repository.

Recommended `.gitignore` entries:

```gitignore
.env
.env.*
!.env.example

*.key
*.pem
serviceAccountKey.json

vpn_configs/*.conf
!vpn_configs/.gitkeep

__pycache__/
*.py[cod]
.venv/
venv/
```

**Important:** Confirm the actual secret-file paths used by your deployment before publishing the repository.

---

## ⚠️ Known Limitations & Compatibility

GhostGrid is a web proxy, not a complete Chromium or headless-browser environment. It fetches and rewrites remote resources, but it does not reproduce every browser capability.

### 1. Dynamic SPA Applications

Modern single-page applications may depend on complex JavaScript execution, cross-origin API requests, WebSockets, and browser-specific behavior.

Some of these operations may not work correctly through a rewritten proxy environment.

### 2. Advanced Anti-Bot Protection

Websites protected by systems such as Cloudflare Turnstile or PerimeterX may require:

- Advanced JavaScript execution.
- Browser fingerprinting.
- Challenge completion.
- Session-specific browser state.
- Additional anti-automation checks.

TLS impersonation alone cannot reproduce a complete browser environment or guarantee successful access.

### 3. Dynamic Search APIs

A website's homepage may load successfully while its subsequent XHR or `fetch()` requests fail due to origin restrictions, authentication requirements, anti-bot checks, or unsupported request patterns.

### 4. VPN Hosting Restrictions

Cloud hosting platforms may impose restrictions on network interfaces, subprocesses, UDP traffic, or VPN routing. WireGuard and Wireproxy behavior must be verified in the actual deployment environment.

### 5. Resource Consumption

Large pages, image-heavy websites, and concurrent browsing sessions can increase memory, CPU, and network usage. Production deployments should include appropriate request limits, timeouts, and resource monitoring.

---

## 🔧 Troubleshooting

| Issue | What to Check |
|---|---|
| Application does not start | Python version, dependencies, environment variables, and startup logs |
| VPN connection fails | WireGuard configuration, Wireproxy binary, permissions, and network access |
| Egress IP does not change | SOCKS5 routing configuration and actual outbound request path |
| Images or CSS do not load | HTML/CSS rewriting and relative URL handling |
| Navigation escapes proxy | JavaScript shim, service worker registration, and navigation interception |
| Website displays a bot challenge | Target website's anti-bot policy and browser compatibility limitations |
| Firebase authentication fails | Firebase project configuration and service account permissions |

---

## 🗺️ Project Roadmap

Potential engineering improvements:

- [ ] More comprehensive HTML and CSS resource rewriting.
- [ ] Improved Service Worker navigation interception.
- [ ] Stronger isolation between concurrent user sessions.
- [ ] Better WebSocket and dynamic API compatibility.
- [ ] VPN tunnel health monitoring and automatic recovery.
- [ ] Configurable VPN server selection.
- [ ] Request rate limiting and abuse prevention.
- [ ] Structured logging and production monitoring.
- [ ] Automated security and compatibility tests.

---

## 📜 Disclaimer

GhostGrid is intended for educational, development, privacy, and authorized network-access purposes.

Users are responsible for complying with applicable laws, VPN provider policies, and the Terms of Service of the websites they access.

GhostGrid does not guarantee access to geo-restricted services, bypass of anti-bot systems, or compatibility with every website. It should not be used to evade access controls or violate third-party rights.

---

## 👨‍💻 Author

**Twinkle Roy**

- GitHub: [@twinkleroy139](https://github.com/twinkleroy139)
- Portfolio: [my-portfolio-6d703.web.app](https://my-portfolio-6d703.web.app)

---

<div align="center">

**⚡ GhostGrid — A browser-based approach to VPN-powered web access.**

<sub>Built with Python, FastAPI, Wireproxy, and modern web technologies.</sub>

</div>