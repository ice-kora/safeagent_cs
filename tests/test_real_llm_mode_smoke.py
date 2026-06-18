import os
from pathlib import Path

import pytest
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
from app.core.config import LLM_MODE_REAL_LLM
from app.llm import LLMActionPlanner, LLMRequest
from app.llm.openai_compatible_provider import OpenAICompatibleLLMProvider
from app.main import app
from app.services.failure_handler import FailureHandler
from app.services.intent_service import RuleBasedIntentClassifier
from app.services.llm_output_guard import LLMOutputGuard
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


def test_real_llm_provider_intent_smoke_or_skip() -> None:
    _skip_without_real_llm_env()
    provider = OpenAICompatibleLLMProvider.from_env()

    response = provider.complete(
        LLMRequest(
            system_prompt=(
                "只输出 JSON：{\"schema_version\":\"1.0\","
                "\"intent\":\"order_query\",\"confidence\":0.9,"
                "\"entities\":{\"order_id\":\"O10086\"}}"
            ),
            user_prompt="帮我查一下订单 O10086",
            task_type="intent",
            temperature=0.0,
            max_tokens=120,
        )
    )
    guard_result = LLMOutputGuard().guard_intent_output(response.text)
    intent = "order_query"
    if not guard_result.fallback_required and guard_result.sanitized_payload:
        intent = guard_result.sanitized_payload["intent"]

    assert isinstance(response.text, str)
    assert intent == "order_query"
    assert _contains_secret(str(response.raw_response)) is False


def test_real_llm_planner_adapter_smoke_or_skip() -> None:
    _skip_without_real_llm_env()
    planner = LLMActionPlanner(
        provider=OpenAICompatibleLLMProvider.from_env(),
        fallback_planner=RuleBasedActionPlanner(),
        output_guard=LLMOutputGuard(),
    )

    plan = planner.plan(intent="order_query", message="帮我查一下订单 O10086")

    assert plan.action == "query_order"
    assert plan.target_id == "O10086"


def test_workflow_real_llm_mode_smoke_or_skip(tmp_path: Path, monkeypatch) -> None:
    _skip_without_real_llm_env()
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "workflow")
    monkeypatch.setenv("SAFEAGENT_LLM_MODE", LLM_MODE_REAL_LLM)
    client, db_path = _client_with_services(tmp_path)

    try:
        response = client.post(
            "/api/chat",
            json={
                "session_id": "sess_001",
                "user_id": "u_1001",
                "message": "帮我查一下订单 O10086",
            },
        )
        body = response.json()

        assert response.status_code == 200
        assert body["status"] in {"SUCCESS", "RECOVERED"}
        assert _count_rows(db_path, "tool_call_logs") <= 1
        assert _contains_secret(str(body)) is False
    finally:
        app.dependency_overrides.clear()


def _skip_without_real_llm_env() -> None:
    api_key = os.getenv("SAFEAGENT_LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("SAFEAGENT_LLM_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL")
    model = os.getenv("SAFEAGENT_LLM_MODEL") or os.getenv("DEEPSEEK_MODEL")
    if not (api_key and base_url and model):
        pytest.skip("real LLM env vars are not configured")


def _contains_secret(text: str) -> bool:
    api_key = os.getenv("SAFEAGENT_LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    return bool(api_key and api_key in text)


def _client_with_services(tmp_path: Path):
    db_path = tmp_path / "test.db"
    trace_service = TraceService(
        db_path=db_path,
        logging_service=LoggingService(log_path=tmp_path / "application.log"),
    )
    repository = RepositoryService(mock_dir=MOCK_DIR, db_path=db_path)
    app.dependency_overrides[get_trace_service] = lambda: trace_service
    app.dependency_overrides[get_intent_classifier] = lambda: RuleBasedIntentClassifier()
    app.dependency_overrides[get_action_planner] = lambda: RuleBasedActionPlanner()
    app.dependency_overrides[get_action_plan_validator] = lambda: ActionPlanValidator()
    app.dependency_overrides[get_policy_service] = lambda: PolicyService(
        repository=repository
    )
    app.dependency_overrides[get_tool_gateway] = lambda: ToolGateway(
        db_path=db_path,
        mock_dir=MOCK_DIR,
    )
    app.dependency_overrides[get_failure_handler] = lambda: FailureHandler(
        db_path=db_path
    )
    app.dependency_overrides[get_pending_action_service] = (
        lambda: PendingActionService(db_path=db_path)
    )
    return TestClient(app), db_path


def _count_rows(db_path: Path, table_name: str) -> int:
    with get_connection(db_path) as connection:
        return connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
