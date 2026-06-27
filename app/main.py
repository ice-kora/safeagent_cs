from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.chat import router as chat_router
from app.api.checkpoints import router as checkpoints_router
from app.api.channels.feishu import router as feishu_router
from app.api.confirm import router as confirm_router
from app.api.health import router as health_router
from app.api.observability import router as observability_router
from app.services.logging_service import LoggingService
from app.storage.database_config import DB_BACKEND_SQLITE, get_database_settings
from app.storage.db import init_db


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONSOLE_DIR = PROJECT_ROOT / "console"

if get_database_settings().backend == DB_BACKEND_SQLITE:
    init_db()
LoggingService().info("app_initialized", {"service": "safeagent-cs"})

app = FastAPI(title="SafeAgent-CS", version="1.0.0")
app.include_router(health_router, prefix="/api", tags=["health"])
app.include_router(chat_router, prefix="/api", tags=["chat"])
app.include_router(confirm_router, prefix="/api", tags=["confirm"])
app.include_router(observability_router, prefix="/api", tags=["observability"])
app.include_router(checkpoints_router, prefix="/api", tags=["checkpoints"])
app.include_router(feishu_router, prefix="/api", tags=["channels"])

if CONSOLE_DIR.exists():
    app.mount("/console", StaticFiles(directory=CONSOLE_DIR, html=True), name="console")


@app.get("/", include_in_schema=False)
def console_redirect():
    if CONSOLE_DIR.exists():
        return RedirectResponse(url="/console/")
    return {"service": "safeagent-cs"}
