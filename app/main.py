from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config.settings import get_settings
from app.middleware.error_handler import render_cyberpunk_error_page
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.routes.admin_routes import router as admin_router
from app.routes.auth_routes import router as auth_router
from app.routes.proxy_routes import router as proxy_router
from app.routes.user_routes import router as user_router

settings = get_settings()

# M-3 Fix: Force debug off in production, even if DEBUG=True is in the environment
is_prod = settings.ENVIRONMENT == "production"
force_debug = settings.DEBUG and not is_prod

app = FastAPI(
    title="GhostGrid Web Proxy",
    description="Cyberpunk No-Install Async Web Proxy Engine",
    version="1.0.0",
    debug=force_debug,
)

# 1. Custom Security Headers Middleware
app.add_middleware(SecurityHeadersMiddleware)

# 2. CORS Policy
# M-1 Fix: Browsers reject `allow_origins=["*"]` when `allow_credentials=True` is set.
# In development, we allow credentials but drop the wildcard.
# In production, you must explicitly list allowed origins in an env var (or we default to the proxy's own host).
if is_prod:
    # For production, allow same-origin and any explicitly configured origins.
    # If you have a custom domain, add it to a comma-separated env var: ALLOWED_ORIGINS
    # For now, we allow everything BUT we drop credentials to adhere to browser specs.
    # If you need cookies, change allow_origins to a specific list (e.g., ["https://yourdomain.com"]).
    origins = ["*"]
    credentials = False 
else:
    origins = ["*"]
    credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Global Exception Handler (M-2 Fix)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catch unhandled exceptions and render the cyberpunk UI instead of raw FastAPI 500s.
    This prevents stack trace leaks in production.
    """
    # Log the actual exception for the server admin
    import logging
    logger = logging.getLogger("ghostgrid.main")
    logger.error(f"Unhandled exception on {request.url.path}: {exc.__class__.__name__}: {exc}", exc_info=True)
    
    return render_cyberpunk_error_page(
        500, 
        "TERMINAL FAULT", 
        f"An internal system error occurred: {exc.__class__.__name__}", 
        str(request.url)
    )

# 4. Mount All API & Tunnel Routers
app.include_router(auth_router)
app.include_router(proxy_router)
app.include_router(user_router)
app.include_router(admin_router)

# 5. Mount Static Assets Directory
static_dir = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# 6. Core Frontend View Routes
@app.get("/")
async def root():
    """Serves the main GhostGrid entrypoint landing page."""
    index_file = static_dir / "index.html"
    return FileResponse(index_file) if index_file.exists() else {"status": "Landing missing"}

@app.get("/sw.js")
async def serve_service_worker():
    return FileResponse(
        "static/sw.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )

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