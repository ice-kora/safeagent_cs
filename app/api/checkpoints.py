from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.services.checkpoint_service import (
    CheckpointError,
    CheckpointPermissionError,
    CheckpointService,
)
from app.services.pending_action_service import PendingActionError
from app.services.resume_service import ResumeError, ResumeService


router = APIRouter()


class CheckpointActionRequest(BaseModel):
    user_id: str
    session_id: str


def get_checkpoint_service() -> CheckpointService:
    return CheckpointService()


def get_resume_service() -> ResumeService:
    return ResumeService()


@router.get("/checkpoints")
def list_checkpoints(
    user_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    checkpoint_service: CheckpointService = Depends(get_checkpoint_service),
) -> list[dict[str, Any]]:
    return checkpoint_service.list_resumable_checkpoints(
        user_id=user_id,
        session_id=session_id,
    )


@router.get("/checkpoints/{checkpoint_id}")
def get_checkpoint(
    checkpoint_id: str,
    checkpoint_service: CheckpointService = Depends(get_checkpoint_service),
) -> dict[str, Any]:
    try:
        return checkpoint_service.get_checkpoint(checkpoint_id)
    except CheckpointError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/checkpoints/{checkpoint_id}/resume")
def resume_checkpoint(
    checkpoint_id: str,
    request: CheckpointActionRequest,
    resume_service: ResumeService = Depends(get_resume_service),
) -> dict[str, Any]:
    try:
        return resume_service.resume_from_checkpoint(
            checkpoint_id=checkpoint_id,
            user_id=request.user_id,
            session_id=request.session_id,
        )
    except CheckpointPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (CheckpointError, ResumeError, PendingActionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/checkpoints/{checkpoint_id}/cancel")
def cancel_checkpoint(
    checkpoint_id: str,
    request: CheckpointActionRequest,
    resume_service: ResumeService = Depends(get_resume_service),
) -> dict[str, Any]:
    try:
        checkpoint = resume_service.cancel_checkpoint(
            checkpoint_id=checkpoint_id,
            user_id=request.user_id,
            session_id=request.session_id,
        )
        return {
            "checkpoint_id": checkpoint_id,
            "status": checkpoint["status"],
            "message": "已取消恢复任务",
            "checkpoint": checkpoint,
        }
    except CheckpointPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (CheckpointError, PendingActionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
