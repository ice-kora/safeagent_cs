from fastapi import FastAPI

from app.api.chat import router as chat_router
from app.api.confirm import router as confirm_router
from app.api.health import router as health_router
from app.services.logging_service import LoggingService
from app.storage.db import init_db


init_db()
LoggingService().info("app_initialized", {"service": "safeagent-cs"})

app = FastAPI(title="SafeAgent-CS", version="0.1.0")
app.include_router(health_router, prefix="/api", tags=["health"])
app.include_router(chat_router, prefix="/api", tags=["chat"])
app.include_router(confirm_router, prefix="/api", tags=["confirm"])
