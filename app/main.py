from fastapi import FastAPI

from app.api.health import router as health_router
from app.services.logging_service import LoggingService
from app.storage.db import init_db


init_db()
LoggingService().info("app_initialized", {"service": "safeagent-cs"})

app = FastAPI(title="SafeAgent-CS", version="0.1.0")
app.include_router(health_router, prefix="/api", tags=["health"])
