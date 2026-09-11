"""
dashboard.py — FastAPI approval dashboard + embedded agent scheduler.

Start: python dashboard.py
Open:  http://localhost:8000
"""
import secrets
import traceback
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

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
    # Lazy-import agent so a broken OPENROUTER_API_KEY never stops the server
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        import agent as _agent

        scheduler = AsyncIOScheduler()
        # 00:30 UTC Mon–Fri = 06:00 IST
        scheduler.add_job(_agent.run, CronTrigger.from_crontab("30 0 * * 1-5"), id="agent_run")
        scheduler.start()
        app.state.scheduler = scheduler
        app.state.agent = _agent
    except Exception as exc:
        print(f"[WARNING] Scheduler failed to start: {exc}")
        app.state.scheduler = None
        app.state.agent = None

    yield

    if getattr(app.state, "scheduler", None):
        app.state.scheduler.shutdown()


app = FastAPI(title="Content Agent Dashboard", lifespan=lifespan)
templates = Jinja2Templates(directory="templates")


_flash: dict | None = None


def _pop_flash() -> dict | None:
    global _flash
    f, _flash = _flash, None
    return f


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/debug")
async def debug():
    try:
        p = store.list_pending()
        a = store.list_approved()
        scheduler_ok = getattr(app.state, "scheduler", None) is not None
        last_error = getattr(app.state, "last_agent_error", None)
        return {"status": "ok", "pending": len(p), "approved": len(a),
                "scheduler": scheduler_ok, "last_agent_error": last_error}
    except Exception as exc:
        return {"error": str(exc), "traceback": traceback.format_exc()}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, tab: str = "pending", _=Depends(verify)):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
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
async def run_agent_now(request: Request, _=Depends(verify)):
    """Trigger one agent run immediately (useful for testing)."""
    import asyncio
    _agent = getattr(request.app.state, "agent", None)
    if _agent is None:
        try:
            import agent as _agent
            request.app.state.agent = _agent
        except Exception as exc:
            return {"error": f"Agent failed to load: {exc}"}

    async def _run_with_logging():
        try:
            await _agent.run()
        except Exception as exc:
            msg = f"[AGENT ERROR] {type(exc).__name__}: {exc}\n{traceback.format_exc()}"
            print(msg, flush=True)
            request.app.state.last_agent_error = msg

    asyncio.create_task(_run_with_logging())
    return {"status": "started"}


@app.get("/approved", response_class=HTMLResponse)
async def approved_tab(request: Request):
    return RedirectResponse(url="/?tab=approved", status_code=302)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("dashboard:app", host=DASHBOARD_HOST, port=DASHBOARD_PORT, reload=False)
