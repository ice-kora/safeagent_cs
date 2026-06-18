from pathlib import Path

from app.core.failure_result import FailureHandlingStatus, FailureNextAction
from app.core.tool_result import ToolError, ToolResult
from app.services.failure_handler import FailureHandler
from app.services.tool_gateway import ToolGateway
from app.storage.db import get_connection, init_db


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = PROJECT_ROOT / "app" / "mock_platform"


class FakeToolGateway:
    """用于确认 FailureHandler 只能通过网关重试的最小替身。"""

    def __init__(self, retry_result: ToolResult) -> None:
        self.retry_result = retry_result
        self.calls: list[dict[str, object]] = []

    def call_tool(
        self,
        run_id: str,
        session_id: str,
        tool_name: str,
        tool_args: dict,
        attempt_no: int = 1,
    ) -> ToolResult:
        self.calls.append(
            {
                "run_id": run_id,
                "session_id": session_id,
                "tool_name": tool_name,
                "tool_args": tool_args,
                "attempt_no": attempt_no,
            }
        )
        return self.retry_result


def _read_failure_logs(db_path: Path) -> list[dict[str, object]]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT run_id, session_id, failure_type, source, retryable,
                   retry_count, fallback_action, final_status
            FROM failure_logs
            ORDER BY created_at ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def _read_tool_logs(db_path: Path) -> list[dict[str, object]]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT run_id, session_id, tool_name, attempt_no,
                   status, failure_type
            FROM tool_call_logs
            ORDER BY created_at ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def _retryable_timeout_result() -> ToolResult:
    return ToolResult(
        success=False,
        tool_name="order_tool.query_order",
        data={},
        summary="工具超时。",
        error_type="TOOL_TIMEOUT",
        error=ToolError(
            failure_type="TOOL_TIMEOUT",
            message="工具超时",
            retryable=True,
        ),
    )


def test_success_tool_result_returns_no_failure_and_does_not_write_log(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test.db"
    handler = FailureHandler(db_path=db_path)
    tool_result = ToolResult(
        success=True,
        tool_name="knowledge_tool.query_policy",
        data={"answer": "ok"},
        summary="ok",
    )

    result = handler.handle_tool_result(
        run_id="run_001",
        session_id="sess_001",
        tool_result=tool_result,
    )

    assert result.status == FailureHandlingStatus.NO_FAILURE
    assert result.retryable is False
    assert result.next_action == FailureNextAction.NO_FAILURE
    assert _read_failure_logs(db_path) == []


def test_retryable_failure_returns_retry_required_and_writes_log(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test.db"
    handler = FailureHandler(db_path=db_path)
    tool_result = ToolResult(
        success=False,
        tool_name="order_tool.query_order",
        data={},
        summary="工具超时。",
        error_type="TOOL_TIMEOUT",
        error=ToolError(
            failure_type="TOOL_TIMEOUT",
            message="工具超时",
            retryable=True,
        ),
    )

    result = handler.handle_tool_result(
        run_id="run_002",
        session_id="sess_001",
        tool_result=tool_result,
    )
    logs = _read_failure_logs(db_path)

    assert result.status == FailureHandlingStatus.RETRY_REQUIRED
    assert result.retryable is True
    assert result.next_action == FailureNextAction.RETRY
    assert len(logs) == 1
    assert logs[0]["failure_type"] == "TOOL_TIMEOUT"
    assert logs[0]["source"] == "tool_gateway"
    assert logs[0]["retryable"] == 1
    assert logs[0]["retry_count"] == 0
    assert logs[0]["fallback_action"] == "RETRY"
    assert logs[0]["final_status"] == "RETRY_REQUIRED"


def test_non_retryable_failure_returns_failed_and_writes_log(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test.db"
    handler = FailureHandler(db_path=db_path)
    tool_result = ToolResult(
        success=False,
        tool_name="unknown_tool.export_all_users",
        data={},
        summary="工具未进入显式安全白名单，已拒绝执行。",
        error_type="TOOL_NOT_IN_ALLOWLIST",
        error=ToolError(
            failure_type="TOOL_NOT_IN_ALLOWLIST",
            message="工具未进入显式安全白名单",
            retryable=False,
        ),
    )

    result = handler.handle_tool_result(
        run_id="run_003",
        session_id="sess_001",
        tool_result=tool_result,
    )
    logs = _read_failure_logs(db_path)

    assert result.status == FailureHandlingStatus.FAILED
    assert result.retryable is False
    assert result.next_action == FailureNextAction.FAILED
    assert len(logs) == 1
    assert logs[0]["failure_type"] == "TOOL_NOT_IN_ALLOWLIST"
    assert logs[0]["retryable"] == 0
    assert logs[0]["fallback_action"] == "FAILED"
    assert logs[0]["final_status"] == "FAILED"


def test_failure_handler_uses_error_failure_type_when_error_type_missing(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test.db"
    handler = FailureHandler(db_path=db_path)
    tool_result = ToolResult(
        success=False,
        tool_name="order_tool.query_order",
        data={},
        summary="订单不存在。",
        error=ToolError(
            failure_type="ORDER_NOT_FOUND",
            message="订单不存在",
            retryable=False,
        ),
    )

    result = handler.handle_tool_result(
        run_id="run_004",
        session_id="sess_001",
        tool_result=tool_result,
    )
    logs = _read_failure_logs(db_path)

    assert result.status == FailureHandlingStatus.FAILED
    assert logs[0]["failure_type"] == "ORDER_NOT_FOUND"
    assert logs[0]["final_status"] == "FAILED"


def test_handle_with_retry_success_first_result_does_not_retry(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test.db"
    handler = FailureHandler(db_path=db_path)
    first_result = ToolResult(
        success=True,
        tool_name="knowledge_tool.query_policy",
        data={"answer": "ok"},
        summary="ok",
    )
    fake_gateway = FakeToolGateway(
        retry_result=ToolResult(
            success=True,
            tool_name="knowledge_tool.query_policy",
            data={},
            summary="retry should not run",
        )
    )

    result = handler.handle_with_retry(
        run_id="run_005",
        session_id="sess_001",
        tool_name="knowledge_tool.query_policy",
        tool_args={"query": "七天无理由"},
        first_result=first_result,
        tool_gateway=fake_gateway,
    )

    assert result.status == FailureHandlingStatus.NO_FAILURE
    assert fake_gateway.calls == []
    assert _read_failure_logs(db_path) == []


def test_handle_with_retry_non_retryable_failure_does_not_retry(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test.db"
    handler = FailureHandler(db_path=db_path)
    first_result = ToolResult(
        success=False,
        tool_name="unknown_tool.export_all_users",
        data={},
        summary="工具未进入显式安全白名单。",
        error_type="TOOL_NOT_IN_ALLOWLIST",
        error=ToolError(
            failure_type="TOOL_NOT_IN_ALLOWLIST",
            message="工具未进入显式安全白名单",
            retryable=False,
        ),
    )
    fake_gateway = FakeToolGateway(retry_result=first_result)

    result = handler.handle_with_retry(
        run_id="run_006",
        session_id="sess_001",
        tool_name="unknown_tool.export_all_users",
        tool_args={},
        first_result=first_result,
        tool_gateway=fake_gateway,
    )
    logs = _read_failure_logs(db_path)

    assert result.status == FailureHandlingStatus.FAILED
    assert fake_gateway.calls == []
    assert len(logs) == 1
    assert logs[0]["retry_count"] == 0
    assert logs[0]["final_status"] == "FAILED"


def test_handle_with_retry_retryable_failure_recovers_through_tool_gateway(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test.db"
    handler = FailureHandler(db_path=db_path)
    gateway = ToolGateway(db_path=db_path, mock_dir=MOCK_DIR)

    result = handler.handle_with_retry(
        run_id="run_007",
        session_id="sess_001",
        tool_name="knowledge_tool.query_policy",
        tool_args={"query": "七天无理由"},
        first_result=_retryable_timeout_result(),
        tool_gateway=gateway,
        current_attempt_no=1,
    )
    failure_logs = _read_failure_logs(db_path)
    tool_logs = _read_tool_logs(db_path)

    assert result.status == FailureHandlingStatus.RECOVERED
    assert result.next_action == FailureNextAction.NO_FAILURE
    assert result.final_tool_result.success is True
    assert len(tool_logs) == 1
    assert tool_logs[0]["tool_name"] == "knowledge_tool.query_policy"
    assert tool_logs[0]["attempt_no"] == 2
    assert tool_logs[0]["status"] == "SUCCESS"
    assert len(failure_logs) == 1
    assert failure_logs[0]["failure_type"] == "TOOL_TIMEOUT"
    assert failure_logs[0]["retryable"] == 1
    assert failure_logs[0]["retry_count"] == 1
    assert failure_logs[0]["fallback_action"] == "RETRY"
    assert failure_logs[0]["final_status"] == "RECOVERED"


def test_handle_with_retry_retryable_failure_still_failed_after_retry(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test.db"
    handler = FailureHandler(db_path=db_path)
    gateway = ToolGateway(db_path=db_path, mock_dir=MOCK_DIR)

    result = handler.handle_with_retry(
        run_id="run_008",
        session_id="sess_001",
        tool_name="order_tool.query_order",
        tool_args={"order_id": "O99999"},
        first_result=_retryable_timeout_result(),
        tool_gateway=gateway,
        current_attempt_no=1,
    )
    failure_logs = _read_failure_logs(db_path)
    tool_logs = _read_tool_logs(db_path)

    assert result.status == FailureHandlingStatus.FAILED
    assert result.next_action == FailureNextAction.FAILED
    assert result.final_tool_result.success is False
    assert len(tool_logs) == 1
    assert tool_logs[0]["tool_name"] == "order_tool.query_order"
    assert tool_logs[0]["attempt_no"] == 2
    assert tool_logs[0]["status"] == "FAILED"
    assert len(failure_logs) == 1
    assert failure_logs[0]["retry_count"] == 1
    assert failure_logs[0]["fallback_action"] == "RETRY"
    assert failure_logs[0]["final_status"] == "FAILED"


def test_handle_with_retry_uses_gateway_call_tool_attempt_two(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test.db"
    handler = FailureHandler(db_path=db_path)
    retry_result = ToolResult(
        success=True,
        tool_name="knowledge_tool.query_policy",
        data={"answer": "ok"},
        summary="ok",
    )
    fake_gateway = FakeToolGateway(retry_result=retry_result)

    handler.handle_with_retry(
        run_id="run_009",
        session_id="sess_001",
        tool_name="knowledge_tool.query_policy",
        tool_args={"query": "七天无理由"},
        first_result=_retryable_timeout_result(),
        tool_gateway=fake_gateway,
        current_attempt_no=1,
    )

    assert fake_gateway.calls == [
        {
            "run_id": "run_009",
            "session_id": "sess_001",
            "tool_name": "knowledge_tool.query_policy",
            "tool_args": {"query": "七天无理由"},
            "attempt_no": 2,
        }
    ]
