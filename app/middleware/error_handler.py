from fastapi import Request
from fastapi.responses import HTMLResponse


def render_cyberpunk_error_page(status_code: int, title: str, message: str, target_url: str = "") -> HTMLResponse:
    """
    Renders a unified, aesthetic Cyberpunk HUD error page for all proxy exceptions.
    """
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>GhostGrid // Terminal Fault {status_code}</title>
  <link rel="stylesheet" href="/static/css/style.css">
</head>
<body style="display:flex; align-items:center; justify-content:center; min-height:100vh; padding:2rem;">
  <div class="cyber-card" style="max-width:650px; width:100%; padding:2.5rem; border-color:var(--neon-magenta); box-shadow:0 0 15px rgba(255,0,85,0.4);">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1.5rem; border-bottom:1px solid rgba(255,0,85,0.3); padding-bottom:0.75rem;">
      <span style="color:var(--neon-magenta); font-weight:700; letter-spacing:2px;">[!] INTERCEPT FAULT // CODE_{status_code}</span>
      <span style="color:var(--neon-amber); font-size:0.85rem;">STATUS: BLOCKED</span>
    </div>

    <h2 style="color:var(--text-primary); font-size:1.4rem; margin-bottom:1rem;">{title}</h2>
    <p style="color:var(--text-muted); font-size:0.95rem; line-height:1.6; margin-bottom:1.5rem;">{message}</p>

    {f'<div style="background:rgba(0,0,0,0.6); padding:0.75rem 1rem; border:1px dashed rgba(255,0,85,0.4); font-size:0.85rem; color:var(--neon-cyan); margin-bottom:1.5rem; word-break:break-all;">TARGET: {target_url}</div>' if target_url else ''}

    <div style="display:flex; gap:1rem;">
      <a href="/browser" class="cyber-btn" style="text-decoration:none; display:inline-block;">RETURN TO CONSOLE</a>
      <a href="/" class="cyber-btn cyber-btn-magenta" style="text-decoration:none; display:inline-block;">MAIN TERMINAL</a>
    </div>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html_content, status_code=status_code)