import json
from pathlib import Path

from app.services.tool_gateway import ToolGateway
from app.storage.db import get_connection


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = PROJECT_ROOT / "app" / "mock_platform"


def _read_tool_logs(db_path: Path) -> list[dict[str, object]]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT run_id, session_id, tool_name, attempt_no,
                   tool_args_json, tool_result_summary_json,
                   status, failure_type, latency_ms
            FROM tool_call_logs
            ORDER BY created_at ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def test_gateway_calls_query_policy_and_writes_log(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    gateway = ToolGateway(db_path=db_path, mock_dir=MOCK_DIR)

    result = gateway.call_tool(
        run_id="run_001",
        session_id="sess_001",
        tool_name="knowledge_tool.query_policy",
        tool_args={"query": "你们支持七天无理由退货吗？"},
    )

    logs = _read_tool_logs(db_path)

    assert result.success is True
    assert result.data["answer"]
    assert result.data["sources"]
    assert len(logs) == 1
    assert logs[0]["tool_name"] == "knowledge_tool.query_policy"
    assert logs[0]["status"] == "SUCCESS"
    assert logs[0]["attempt_no"] == 1


def test_gateway_calls_query_order_and_returns_sanitized_result(
    tmp_path: Path,
) -> None:
    gateway = ToolGateway(db_path=tmp_path / "test.db", mock_dir=MOCK_DIR)

    result = gateway.call_tool(
        run_id="run_002",
        session_id="sess_001",
        tool_name="order_tool.query_order",
        tool_args={"order_id": "O10086"},
    )
    result_json = json.dumps(result.to_dict(), ensure_ascii=False)

    assert result.success is True
    assert result.data["order_id"] == "O10086"
    assert "phone" not in result.data
    assert "address" not in result.data
    assert "payment_info" not in result.data
    assert "13800001234" not in result_json
    assert "Henan Zhengzhou Jinshui Road 100" not in result_json
    assert "card_123456" not in result_json


def test_gateway_rejects_unknown_tool_and_logs_failure(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    gateway = ToolGateway(db_path=db_path, mock_dir=MOCK_DIR)

    result = gateway.call_tool(
        run_id="run_003",
        session_id="sess_001",
        tool_name="unknown_tool.export_all_users",
        tool_args={"phone": "13800001234"},
    )
    logs = _read_tool_logs(db_path)

    assert result.success is False
    assert result.error_type == "TOOL_NOT_IN_ALLOWLIST"
    assert len(logs) == 1
    assert logs[0]["status"] == "FAILED"
    assert logs[0]["failure_type"] == "TOOL_NOT_IN_ALLOWLIST"


def test_gateway_writes_sanitized_tool_args_and_result_summary(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test.db"
    gateway = ToolGateway(db_path=db_path, mock_dir=MOCK_DIR)

    gateway.call_tool(
        run_id="run_004",
        session_id="sess_001",
        tool_name="order_tool.change_address",
        tool_args={
            "order_id": "O10086",
            "new_address": "Very Sensitive Full Address 999",
            "phone": "13800001234",
            "payment_info": "card_123456",
            "token": "tok_secret_123",
            "api_key": "key_secret_123",
            "system_prompt": "internal prompt",
            "authorization": "Bearer abc",
        },
    )
    log = _read_tool_logs(db_path)[0]

    args_json = str(log["tool_args_json"])
    result_summary_json = str(log["tool_result_summary_json"])
    combined_log_json = args_json + result_summary_json

    assert "Very Sensitive Full Address 999" not in combined_log_json
    assert "13800001234" not in combined_log_json
    assert "card_123456" not in combined_log_json
    assert "tok_secret_123" not in combined_log_json
    assert "key_secret_123" not in combined_log_json
    assert "internal prompt" not in combined_log_json
    assert "Bearer abc" not in combined_log_json
    assert json.loads(args_json)["new_address"] == "***"
    assert json.loads(result_summary_json)["summary"]


def test_gateway_writes_one_log_per_call_with_default_attempt_no(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test.db"
    gateway = ToolGateway(db_path=db_path, mock_dir=MOCK_DIR)

    gateway.call_tool(
        run_id="run_005",
        session_id="sess_001",
        tool_name="knowledge_tool.query_policy",
        tool_args={"query": "发票"},
    )
    gateway.call_tool(
        run_id="run_005",
        session_id="sess_001",
        tool_name="knowledge_tool.query_policy",
        tool_args={"query": "退款政策"},
    )
    logs = _read_tool_logs(db_path)

    assert len(logs) == 2
    assert [log["attempt_no"] for log in logs] == [1, 1]


def test_gateway_does_not_do_policy_check(tmp_path: Path) -> None:
    gateway = ToolGateway(db_path=tmp_path / "test.db", mock_dir=MOCK_DIR)

    result = gateway.call_tool(
        run_id="run_006",
        session_id="sess_001",
        tool_name="order_tool.query_order",
        tool_args={"order_id": "O10087"},
    )

    assert result.success is True
    assert result.data["order_id"] == "O10087"
