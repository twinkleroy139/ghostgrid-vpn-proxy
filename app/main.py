from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config.settings import get_settings
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.routes.admin_routes import router as admin_router
from app.routes.auth_routes import router as auth_router
from app.routes.proxy_routes import router as proxy_router
from app.routes.user_routes import router as user_router

settings = get_settings()

app = FastAPI(
    title="GhostGrid Web Proxy",
    description="Cyberpunk No-Install Async Web Proxy Engine",
    version="1.0.0",
    debug=settings.DEBUG,
)

# 1. Custom Security Headers Middleware
app.add_middleware(SecurityHeadersMiddleware)

# 2. CORS Policy
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Mount All API & Tunnel Routers
app.include_router(auth_router)
app.include_router(proxy_router)
app.include_router(user_router)
app.include_router(admin_router)

# 4. Mount Static Assets Directory
static_dir = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# 5. Core Frontend View Routes
@app.get("/")
async def root():
    """Serves the main GhostGrid entrypoint landing page."""
    index_file = static_dir / "index.html"
    return FileResponse(index_file) if index_file.exists() else {"status": "Landing missing"}


@app.get("/browser")
async def browser_view():
    """Serves the GhostGrid browser workspace."""
    browser_file = static_dir / "browser.html"
    return FileResponse(browser_file) if browser_file.exists() else {"status": "Browser view missing"}


@app.get("/dashboard")
async def dashboard_view():
    """Serves the Operative telemetry and bookmarks dashboard."""
    dashboard_file = static_dir / "dashboard.html"
    return FileResponse(dashboard_file) if dashboard_file.exists() else {"status": "Dashboard view missing"}


@app.get("/admin")
async def admin_view():
    """Serves the Admin Command Node."""
    admin_file = static_dir / "admin.html"
    return FileResponse(admin_file) if admin_file.exists() else {"status": "Admin view missing"}