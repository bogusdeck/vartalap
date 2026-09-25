from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Security, Depends, status, BackgroundTasks
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from vartalap.settings import get_settings, reload_settings
from vartalap.agent_loop import run_agent
from vartalap.logger import get_recent_logs, init_db
from vartalap.scheduler import start_scheduler, stop_scheduler, poll_unread_dms_job

app = FastAPI(
    title="Vartalap API",
    description="Autonomous Reddit DM agent service",
    version="0.1.0"
)

# Auth Schemes
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


def verify_api_key(
    header_key: Optional[str] = Security(api_key_header),
    bearer: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
):
    """Verify incoming request against configured security API key."""
    settings = get_settings()
    configured_key = settings.security.api_key

    # If no key is set in config/env, allow access or warn
    if not configured_key or configured_key == "test_secret_key":
        return True

    provided_key = header_key or (bearer.credentials if bearer else None)

    if not provided_key or provided_key != configured_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key"
        )
    return True


class RunRequest(BaseModel):
    username: str = Field(..., example="elonmusk")
    instruction: str = Field(..., example="Reply to Elon, keep the tone casual")
    dry_run: Optional[bool] = Field(default=None, example=True)


@app.on_event("startup")
async def startup_event():
    """Initialize database and start scheduler on startup."""
    init_db()
    settings = get_settings()
    start_scheduler()
    print(f"[API] Vartalap service started. Active LLM backend: '{settings.llm.backend}'")


@app.on_event("shutdown")
async def shutdown_event():
    """Stop background scheduler on shutdown."""
    stop_scheduler()
    print("[API] Vartalap service stopped.")


@app.get("/health", tags=["Health"])
async def health_check():
    """Service health check endpoint."""
    settings = get_settings()
    return {
        "status": "healthy",
        "llm_backend": settings.llm.backend,
        "dry_run_default": settings.agent.dry_run,
        "scheduler_interval": settings.scheduler.polling_interval_minutes
    }


@app.post("/run", tags=["Agent"], dependencies=[Depends(verify_api_key)])
async def trigger_run(req: RunRequest):
    """Trigger an autonomous conversation agent run for a specific Reddit username."""
    try:
        result = await run_agent(
            username=req.username,
            instruction=req.instruction,
            dry_run=req.dry_run
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent run failed: {str(e)}"
        )


@app.post("/scheduler/tick", tags=["Scheduler"], dependencies=[Depends(verify_api_key)])
async def trigger_scheduler_tick(background_tasks: BackgroundTasks):
    """Manually trigger a scheduler polling tick in the background."""
    background_tasks.add_task(poll_unread_dms_job)
    return {"status": "scheduled", "message": "Manual scheduler tick launched in background"}


@app.get("/logs", tags=["Logs"], dependencies=[Depends(verify_api_key)])
async def fetch_logs(limit: int = 50, username: Optional[str] = None):
    """Retrieve recent action logs with optional limit and username filter."""
    try:
        logs = get_recent_logs(limit=limit, username=username)
        return {"count": len(logs), "logs": logs}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch logs: {str(e)}"
        )
