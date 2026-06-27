import json
from pathlib import Path
from typing import Any

from app.core.constants import RunStatus, TraceStatus
from app.core.ids import generate_run_id, generate_trace_node_id
from app.services.logging_service import LoggingService
from app.storage.runtime_store import get_runtime_store


class TraceService:
    """Agent 执行链路 Trace 服务。

    每次 /api/chat 或 /api/confirm 都会创建一个 run。
    run 下挂多个 trace 节点，用于解释 Agent 为什么走到某个结果。
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        logging_service: LoggingService | None = None,
    ) -> None:
        self.db_path = Path(db_path) if db_path else None
        self.logging_service = logging_service or LoggingService()
        self.runtime_store = get_runtime_store(db_path=self.db_path)

    def start_run(
        self,
        session_id: str,
        user_id: str,
        request_id: str,
        parent_run_id: str | None = None,
        pending_action_id: str | None = None,
    ) -> str:
        """创建新的 Agent 执行链路。

        parent_run_id 只用于跨请求关联，例如 /api/confirm；
        同一次 run 内的工具重试不会创建新的 run。
        """
        run_id = generate_run_id()
        self.runtime_store.insert_agent_run(
            {
                "run_id": run_id,
                "session_id": session_id,
                "user_id": user_id,
                "request_id": request_id,
                "parent_run_id": parent_run_id,
                "pending_action_id": pending_action_id,
                "status": RunStatus.RUNNING.value,
            }
        )
        self.logging_service.info(
            "agent_run_started",
            {
                "request_id": request_id,
                "session_id": session_id,
                "run_id": run_id,
                "parent_run_id": parent_run_id,
                "pending_action_id": pending_action_id,
            },
        )
        return run_id

    def finish_run(self, run_id: str) -> None:
        """将 run 标记为成功结束。

        start_run 只表示链路开始。如果没有结束状态，后续排查时无法区分
        “仍在执行”和“已经正常完成”，所以这里显式关闭生命周期。
        """
        self._update_run_status(run_id, RunStatus.SUCCESS.value)
        self.logging_service.info("agent_run_finished", {"run_id": run_id})

    def fail_run(self, run_id: str, error_type: str) -> None:
        """将 run 标记为失败结束，并记录失败类型。"""
        self._update_run_status(run_id, RunStatus.FAILED.value)
        self.logging_service.error(
            "agent_run_failed",
            {
                "run_id": run_id,
                "error_type": error_type,
            },
        )

    def append_trace(
        self,
        run_id: str,
        node_name: str,
        input_json: dict[str, Any],
        output_json: dict[str, Any],
        status: str = TraceStatus.SUCCESS.value,
        error_type: str | None = None,
    ) -> str:
        """追加一个 Trace 节点。

        节点输入输出会先脱敏再入库。这样即使后续节点传入了手机号、
        地址或 token，也不会把敏感明文写入 Trace。
        """
        run = self._get_run(run_id)
        trace_node_id = generate_trace_node_id()
        sanitized_input = LoggingService.sanitize_payload(input_json)
        sanitized_output = LoggingService.sanitize_payload(output_json)
        self.runtime_store.insert_agent_trace(
            {
                "trace_node_id": trace_node_id,
                "run_id": run_id,
                "parent_run_id": run["parent_run_id"],
                "session_id": run["session_id"],
                "node_name": node_name,
                "input_json": json.dumps(
                    sanitized_input,
                    ensure_ascii=False,
                    default=str,
                ),
                "output_json": json.dumps(
                    sanitized_output,
                    ensure_ascii=False,
                    default=str,
                ),
                "status": status,
                "error_type": error_type,
            }
        )
        self.logging_service.info(
            "trace_node_appended",
            {
                "run_id": run_id,
                "trace_node_id": trace_node_id,
                "node_name": node_name,
                "status": status,
                "error_type": error_type,
            },
        )
        return trace_node_id

    def get_traces(self, run_id: str) -> list[dict[str, Any]]:
        """按 run_id 读取完整节点链路。"""
        rows = self.runtime_store.list_agent_traces(run_id)
        return [self._trace_row_to_dict(row) for row in rows]

    def _update_run_status(self, run_id: str, status: str) -> None:
        self._get_run(run_id)
        self.runtime_store.update_agent_run_status(run_id, status)

    def _get_run(self, run_id: str) -> dict[str, Any]:
        row = self.runtime_store.get_agent_run(run_id)
        if not row:
            raise ValueError(f"run_id 不存在，无法更新或写入 Trace: {run_id}")
        return row

    @staticmethod
    def _trace_row_to_dict(row: Any) -> dict[str, Any]:
        return {
            "trace_node_id": row["trace_node_id"],
            "run_id": row["run_id"],
            "parent_run_id": row["parent_run_id"],
            "session_id": row["session_id"],
            "node_name": row["node_name"],
            "input_json": json.loads(row["input_json"]),
            "output_json": json.loads(row["output_json"]),
            "status": row["status"],
            "error_type": row["error_type"],
            "created_at": row["created_at"],
        }
