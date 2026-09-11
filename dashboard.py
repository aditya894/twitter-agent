"""
dashboard.py — FastAPI approval dashboard.

Start: python dashboard.py
Open:  http://localhost:8000
"""
import secrets

from fastapi import Depends, FastAPI, HTTPException, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

import store
from config import DASHBOARD_HOST, DASHBOARD_PORT, DASHBOARD_PASSWORD

app = FastAPI(title="Content Agent Dashboard")
templates = Jinja2Templates(directory="templates")
security = HTTPBasic(auto_error=False)

# Flash message stored in-process (simple, no sessions needed)
_flash: dict | None = None


def _pop_flash() -> dict | None:
    global _flash
    f, _flash = _flash, None
    return f


def verify(credentials: HTTPBasicCredentials = Depends(security)):
    if not DASHBOARD_PASSWORD:
        return  # local dev — no auth
    if not credentials:
        raise HTTPException(401, headers={"WWW-Authenticate": "Basic"})
    ok = secrets.compare_digest(
        credentials.password.encode(), DASHBOARD_PASSWORD.encode()
    )
    if not ok:
        raise HTTPException(401, headers={"WWW-Authenticate": "Basic"})


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, tab: str = "pending", _=Depends(verify)):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "pending": store.list_pending(),
            "approved": store.list_approved(),
            "tab": tab,
            "flash": _pop_flash(),
        },
    )


@app.post("/approve/{post_id}")
async def approve(post_id: str, _=Depends(verify)):
    global _flash
    success = store.approve(post_id)
    _flash = (
        {"type": "success", "message": "✅ Post approved."}
        if success
        else {"type": "error", "message": "Post not found."}
    )
    return RedirectResponse(url="/?tab=pending", status_code=303)


@app.post("/reject/{post_id}")
async def reject(post_id: str, _=Depends(verify)):
    global _flash
    success = store.reject(post_id)
    _flash = (
        {"type": "success", "message": "🗑️ Post rejected and removed."}
        if success
        else {"type": "error", "message": "Post not found."}
    )
    return RedirectResponse(url="/?tab=pending", status_code=303)


@app.get("/approved", response_class=HTMLResponse)
async def approved_tab(request: Request):
    return RedirectResponse(url="/?tab=approved", status_code=302)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("dashboard:app", host=DASHBOARD_HOST, port=DASHBOARD_PORT, reload=False)
