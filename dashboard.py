"""
dashboard.py — FastAPI approval dashboard + embedded agent scheduler.

Start: python dashboard.py
Open:  http://localhost:8000

Scheduling: APScheduler runs agent.run() at 00:30 UTC Mon–Fri (06:00 IST)
inside this process so it shares the same SQLite DB as the dashboard.
"""
import secrets
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

import agent
import store
from config import DASHBOARD_HOST, DASHBOARD_PORT, DASHBOARD_PASSWORD

security = HTTPBasic(auto_error=False)


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler()
    # 00:30 UTC Mon–Fri = 06:00 IST
    scheduler.add_job(agent.run, CronTrigger.from_crontab("30 0 * * 1-5"), id="agent_run")
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="Content Agent Dashboard", lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

# Flash message stored in-process (simple, no sessions needed)
_flash: dict | None = None


def _pop_flash() -> dict | None:
    global _flash
    f, _flash = _flash, None
    return f


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


@app.post("/internal/run-agent")
async def run_agent_now(_=Depends(verify)):
    """Trigger one agent run immediately (useful for testing)."""
    import asyncio
    asyncio.create_task(agent.run())
    return {"status": "started"}


@app.get("/approved", response_class=HTMLResponse)
async def approved_tab(request: Request):
    return RedirectResponse(url="/?tab=approved", status_code=302)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("dashboard:app", host=DASHBOARD_HOST, port=DASHBOARD_PORT, reload=False)
