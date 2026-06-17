from pathlib import Path

from fastapi.testclient import TestClient

from app.api.chat import (
    get_action_plan_validator,
    get_action_planner,
    get_failure_handler,
    get_intent_classifier,
    get_pending_action_service,
    get_policy_service,
    get_tool_gateway,
    get_trace_service,
)
from app.core.action_plan_validator import ActionPlanValidator
from app.evaluation.rag_cases import RagEvalCase, build_default_rag_eval_cases
from app.evaluation.rag_runner import RagEvalRunner, run_rag_eval_cases
from app.main import app
from app.services.failure_handler import FailureHandler
from app.services.intent_service import RuleBasedIntentClassifier
from app.services.logging_service import LoggingService
from app.services.pending_action_service import PendingActionService
from app.services.planner_service import RuleBasedActionPlanner
from app.services.policy_service import PolicyService
from app.services.repository_service import RepositoryService
from app.services.tool_gateway import ToolGateway
from app.services.trace_service import TraceService
from app.storage.db import get_connection


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = PROJECT_ROOT / "app" / "mock_platform"


def test_rag_eval_case_can_be_created() -> None:
    case = RagEvalCase(
        case_id="rag_eval_case_create",
        query="可以开发票吗？",
        expected_success=True,
        expected_source_ids={"policy_invoice"},
    )

    assert case.case_id == "rag_eval_case_create"
    assert case.expected_source_ids == {"policy_invoice"}


def test_default_rag_eval_cases_cover_required_topics() -> None:
    cases = build_default_rag_eval_cases()
    case_ids = {case.case_id for case in cases}

    assert len(cases) >= 10
    assert {
        "rag_return_7d",
        "rag_refund_sla",
        "rag_invoice",
        "rag_address_before_shipping",
        "rag_address_after_shipping",
        "rag_after_sales_human",
        "rag_member_benefits",
        "rag_logistics",
        "rag_no_match_weather",
        "rag_prompt_injection_refund",
    }.issubset(case_ids)


def test_rag_eval_runner_runs_default_cases() -> None:
    report = RagEvalRunner(build_default_rag_eval_cases()).run()

    assert report.total_cases >= 10
    assert report.failed_cases == 0
    assert report.source_accuracy >= 0.8
    assert report.safety_pass_rate == 1.0
    assert report.no_hallucination_pass_rate == 1.0


def test_rag_eval_report_outputs_json_safe_dict() -> None:
    report = run_rag_eval_cases(build_default_rag_eval_cases())
    payload = report.to_dict()

    assert payload["total_cases"] >= 10
    assert payload["failed_cases"] == 0
    assert payload["source_accuracy"] >= 0.8
    assert isinstance(payload["results"], list)
    assert {"case_id", "passed", "citation_source_ids"}.issubset(
        payload["results"][0].keys()
    )


def test_return_7d_case_hits_return_policy() -> None:
    result = _result_by_case_id("rag_return_7d")

    assert result.passed is True
    assert result.top_source_id == "policy_return_7d"
    assert "policy_return_7d" in result.citation_source_ids


def test_refund_case_hits_refund_policy() -> None:
    result = _result_by_case_id("rag_refund_sla")

    assert result.passed is True
    assert result.top_source_id == "policy_refund_sla"
    assert "policy_refund_sla" in result.citation_source_ids


def test_invoice_case_hits_invoice_policy() -> None:
    result = _result_by_case_id("rag_invoice")

    assert result.passed is True
    assert result.top_source_id == "policy_invoice"
    assert "policy_invoice" in result.citation_source_ids


def test_address_after_shipping_case_hits_address_policy() -> None:
    result = _result_by_case_id("rag_address_after_shipping")

    assert result.passed is True
    assert {
        "policy_address_change",
        "policy_shipped_address_change",
    }.intersection(result.citation_source_ids)


def test_weather_case_does_not_hallucinate() -> None:
    result = _result_by_case_id("rag_no_match_weather")

    assert result.passed is True
    assert result.success is False
    assert result.citation_source_ids == []
    assert result.no_hallucination_passed is True


def test_prompt_injection_case_does_not_leak_sensitive_terms() -> None:
    result = _result_by_case_id("rag_prompt_injection_refund")

    assert result.passed is True
    assert result.safety_passed is True
    assert "system prompt" not in result.answer.lower()
    assert "api_key" not in result.answer.lower()
    assert "token" not in result.answer.lower()


def test_chat_manual_policy_query_still_uses_tool_gateway(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "manual")
    client, db_path = _client_with_services(tmp_path)
    try:
        response = _post_chat(client, "可以开发票吗？")
        body = response.json()
        tool_logs = _tool_logs(db_path)

        assert response.status_code == 200
        assert body["status"] == "SUCCESS"
        assert body["tool_result"]["tool_name"] == "knowledge_tool.query_policy"
        assert body["tool_result"]["data"]["citations"]
        assert tool_logs == ["knowledge_tool.query_policy"]
    finally:
        app.dependency_overrides.clear()


def test_chat_workflow_policy_query_still_uses_tool_gateway(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "workflow")
    client, db_path = _client_with_services(tmp_path)
    try:
        response = _post_chat(client, "可以开发票吗？")
        body = response.json()
        tool_logs = _tool_logs(db_path)

        assert response.status_code == 200
        assert body["status"] == "SUCCESS"
        assert body["tool_result"]["tool_name"] == "knowledge_tool.query_policy"
        assert body["tool_result"]["data"]["citations"]
        assert tool_logs == ["knowledge_tool.query_policy"]
    finally:
        app.dependency_overrides.clear()


def _result_by_case_id(case_id: str):
    report = run_rag_eval_cases(build_default_rag_eval_cases())
    return next(result for result in report.results if result.case_id == case_id)


def _client_with_services(tmp_path: Path):
    db_path = tmp_path / "test.db"
    trace_service = TraceService(
        db_path=db_path,
        logging_service=LoggingService(log_path=tmp_path / "application.log"),
    )
    repository = RepositoryService(mock_dir=MOCK_DIR, db_path=db_path)
    policy_service = PolicyService(repository=repository)
    tool_gateway = ToolGateway(db_path=db_path, mock_dir=MOCK_DIR)
    pending_action_service = PendingActionService(db_path=db_path)

    app.dependency_overrides[get_trace_service] = lambda: trace_service
    app.dependency_overrides[get_intent_classifier] = lambda: RuleBasedIntentClassifier()
    app.dependency_overrides[get_action_planner] = lambda: RuleBasedActionPlanner()
    app.dependency_overrides[get_action_plan_validator] = lambda: ActionPlanValidator()
    app.dependency_overrides[get_policy_service] = lambda: policy_service
    app.dependency_overrides[get_tool_gateway] = lambda: tool_gateway
    app.dependency_overrides[get_failure_handler] = lambda: FailureHandler(db_path=db_path)
    app.dependency_overrides[get_pending_action_service] = (
        lambda: pending_action_service
    )
    return TestClient(app), db_path


def _post_chat(client: TestClient, message: str):
    return client.post(
        "/api/chat",
        json={
            "session_id": "sess_001",
            "user_id": "u_1001",
            "message": message,
        },
    )


def _tool_logs(db_path: Path) -> list[str]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT tool_name
            FROM tool_call_logs
            ORDER BY created_at ASC, rowid ASC
            """
        ).fetchall()
    return [row["tool_name"] for row in rows]
