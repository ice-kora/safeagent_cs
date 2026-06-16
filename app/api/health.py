from fastapi import APIRouter


router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "safeagent-cs",
        "phase": "p0-phase-1",
    }
