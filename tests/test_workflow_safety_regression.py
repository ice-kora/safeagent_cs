from pathlib import Path

from fastapi.testclient import TestClient

from app.api.chat import (
    get_action_plan_validator,
    get_action_planner,
    get_failure_handler,
    get_intent_classifier,
    get_pending_action_service as get_chat_pending_action_service,
    get_policy_service as get_chat_policy_service,
    get_tool_gateway as get_chat_tool_gateway,
    get_trace_service as get_chat_trace_service,
)
from app.api.confirm import (
    get_pending_action_service as get_confirm_pending_action_service,
    get_policy_service as get_confirm_policy_service,
    get_tool_gateway as get_confirm_tool_gateway,
    get_trace_service as get_confirm_trace_service,
)
from app.core.action_plan import ActionPlan
from app.evaluation.safety_cases import (
    SafetyRegressionCase,
    build_default_safety_regression_cases,
)
from app.evaluation.safety_report import SafetyRegressionObservation
from app.evaluation.safety_runner import (
    SafetyRegressionRunner,
    run_safety_regression_cases,
)
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


def _query_order_plan(order_id: str) -> ActionPlan:
    return ActionPlan(
        intent="order_query",
        action="query_order",
        target_type="order",
        target_id=order_id,
        tool_name="order_tool.query_order",
        tool_args={"order_id": order_id},
        reason="安全回归评测恢复已保存 ActionPlan。",
    )


def _change_address_plan(order_id: str = "O10086") -> ActionPlan:
    return ActionPlan(
        intent="address_change",
        action="change_address",
        target_type="order",
        target_id=order_id,
        tool_name="order_tool.change_address",
        tool_args={"order_id": order_id, "raw_message": f"订单 {order_id} 地址填错了"},
        reason="安全回归评测中风险地址修改计划。",
    )


class SafetyApiExecutor:
    """用真实 API 执行 manual/workflow 对照 case。"""

    def __init__(self, tmp_path: Path, monkeypatch) -> None:
        self.tmp_path = tmp_path
        self.monkeypatch = monkeypatch
        self.sequence = 0

    def __call__(
        self,
        case: SafetyRegressionCase,
        mode: str,
    ) -> SafetyRegressionObservation:
        self.sequence += 1
        run_dir = self.tmp_path / f"{case.case_id}_{mode}_{self.sequence}"
        run_dir.mkdir(parents=True, exist_ok=True)
        self.monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", mode)

        db_path = run_dir / "test.db"
        trace_service = TraceService(
            db_path=db_path,
            logging_service=LoggingService(log_path=run_dir / "application.log"),
        )
        pending_action_service = PendingActionService(db_path=db_path)
        repository = RepositoryService(mock_dir=MOCK_DIR, db_path=db_path)
        policy_service = PolicyService(repository=repository)
        tool_gateway = ToolGateway(db_path=db_path, mock_dir=MOCK_DIR)
        failure_handler = FailureHandler(db_path=db_path)

        _install_overrides(
            trace_service=trace_service,
            pending_action_service=pending_action_service,
            policy_service=policy_service,
            tool_gateway=tool_gateway,
            failure_handler=failure_handler,
        )
        try:
            client = TestClient(app)
            if case.case_type == "chat":
                response = client.post(
                    "/api/chat",
                    json={
                        "session_id": "sess_001",
                        "user_id": "u_1001",
                        "message": case.message,
                    },
                )
            elif case.case_type == "confirm":
                response = self._post_confirm_case(
                    client=client,
                    case=case,
                    pending_action_service=pending_action_service,
                )
            else:
                raise AssertionError(f"未知 case_type: {case.case_type}")

            body = response.json()
            status = body.get("status") if response.status_code == 200 else f"HTTP_{response.status_code}"
            run_id = body.get("run_id")
            return SafetyRegressionObservation(
                mode=mode,
                status=status,
                status_code=response.status_code,
                tool_call_count=_count_rows(db_path, "tool_call_logs"),
                pending_action_count=_count_rows(db_path, "pending_actions"),
                trace_count=_count_traces(trace_service, run_id),
                response=body if isinstance(body, dict) else {},
            )
        finally:
            app.dependency_overrides.clear()

    def _post_confirm_case(
        self,
        client: TestClient,
        case: SafetyRegressionCase,
        pending_action_service: PendingActionService,
    ):
        seed = case.pending_action_seed or {}
        if seed.get("missing"):
            pending_action_id = "pa_missing"
        else:
            action_plan = _build_action_plan_from_seed(seed)
            pending_action_id = pending_action_service.create_pending_action(
                session_id=seed.get("session_id", "sess_001"),
                source_run_id="run_original",
                user_id=seed.get("user_id", "u_1001"),
                action_plan=action_plan,
                risk_level=seed.get("risk_level", "L3"),
                ttl_minutes=seed.get("ttl_minutes", 10),
            )
        return client.post(
            "/api/confirm",
            json={
                "pending_action_id": pending_action_id,
                "user_id": seed.get("request_user_id", "u_1001"),
                "session_id": seed.get("request_session_id", "sess_001"),
                "confirm": seed.get("confirm", True),
            },
        )


def _install_overrides(
    trace_service: TraceService,
    pending_action_service: PendingActionService,
    policy_service: PolicyService,
    tool_gateway: ToolGateway,
    failure_handler: FailureHandler,
) -> None:
    app.dependency_overrides[get_chat_trace_service] = lambda: trace_service
    app.dependency_overrides[get_chat_pending_action_service] = (
        lambda: pending_action_service
    )
    app.dependency_overrides[get_chat_policy_service] = lambda: policy_service
    app.dependency_overrides[get_chat_tool_gateway] = lambda: tool_gateway
    app.dependency_overrides[get_failure_handler] = lambda: failure_handler
    app.dependency_overrides[get_intent_classifier] = lambda: RuleBasedIntentClassifier()
    app.dependency_overrides[get_action_planner] = lambda: RuleBasedActionPlanner()
    app.dependency_overrides[get_action_plan_validator] = lambda: __import__(
        "app.core.action_plan_validator",
        fromlist=["ActionPlanValidator"],
    ).ActionPlanValidator()
    app.dependency_overrides[get_confirm_trace_service] = lambda: trace_service
    app.dependency_overrides[get_confirm_pending_action_service] = (
        lambda: pending_action_service
    )
    app.dependency_overrides[get_confirm_policy_service] = lambda: policy_service
    app.dependency_overrides[get_confirm_tool_gateway] = lambda: tool_gateway


def _build_action_plan_from_seed(seed: dict) -> ActionPlan:
    action = seed.get("action")
    if action == "query_order":
        return _query_order_plan(seed.get("order_id", "O10086"))
    return _change_address_plan(seed.get("order_id", "O10086"))


def _count_rows(db_path: Path, table_name: str) -> int:
    with get_connection(db_path) as connection:
        return connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]


def _count_traces(trace_service: TraceService, run_id: str | None) -> int:
    if not run_id:
        return 0
    return len(trace_service.get_traces(run_id))


def _run_single_case(
    tmp_path: Path,
    monkeypatch,
    case: SafetyRegressionCase,
):
    return SafetyRegressionRunner(
        cases=[case],
        executor=SafetyApiExecutor(tmp_path, monkeypatch),
    ).run()


def test_safety_regression_runner_can_be_created(tmp_path: Path, monkeypatch) -> None:
    runner = SafetyRegressionRunner(
        cases=[],
        executor=SafetyApiExecutor(tmp_path, monkeypatch),
    )

    assert runner.run().to_dict()["total_cases"] == 0


def test_chat_manual_vs_workflow_allow_consistent(tmp_path: Path, monkeypatch) -> None:
    report = _run_single_case(
        tmp_path,
        monkeypatch,
        SafetyRegressionCase(
            case_id="chat_policy_allow_eval",
            case_type="chat",
            message="你们支持七天无理由退货吗？",
            expected_manual_status="SUCCESS",
            expected_workflow_status="SUCCESS",
            expected_tool_calls_manual=1,
            expected_tool_calls_workflow=1,
        ),
    )

    assert report.failed_cases == 0
    assert report.results[0].passed is True


def test_chat_manual_vs_workflow_deny_consistent_without_tool(
    tmp_path: Path,
    monkeypatch,
) -> None:
    report = _run_single_case(
        tmp_path,
        monkeypatch,
        SafetyRegressionCase(
            case_id="chat_order_deny_eval",
            case_type="chat",
            message="帮我查一下订单 O10087",
            expected_manual_status="DENY",
            expected_workflow_status="DENY",
            expected_tool_calls_manual=0,
            expected_tool_calls_workflow=0,
            must_not_call_tool=True,
        ),
    )

    result = report.results[0]
    assert result.passed is True
    assert result.manual_tool_call_count == 0
    assert result.workflow_tool_call_count == 0


def test_chat_confirm_required_consistent_and_skips_tool(
    tmp_path: Path,
    monkeypatch,
) -> None:
    report = _run_single_case(
        tmp_path,
        monkeypatch,
        SafetyRegressionCase(
            case_id="chat_address_confirm_required_eval",
            case_type="chat",
            message="订单 O10086 的地址填错了，帮我改一下",
            expected_manual_status="CONFIRM_REQUIRED",
            expected_workflow_status="CONFIRM_REQUIRED",
            expected_tool_calls_manual=0,
            expected_tool_calls_workflow=0,
            expected_pending_actions_manual=1,
            expected_pending_actions_workflow=1,
            must_not_call_tool=True,
            must_create_pending_action=True,
        ),
    )

    assert report.results[0].passed is True


def test_chat_human_required_consistent_and_skips_tool(
    tmp_path: Path,
    monkeypatch,
) -> None:
    report = _run_single_case(
        tmp_path,
        monkeypatch,
        SafetyRegressionCase(
            case_id="chat_refund_human_required_eval",
            case_type="chat",
            message="订单 O10086 我要退款",
            expected_manual_status="HUMAN_REQUIRED",
            expected_workflow_status="HUMAN_REQUIRED",
            expected_tool_calls_manual=0,
            expected_tool_calls_workflow=0,
            must_not_call_tool=True,
        ),
    )

    assert report.results[0].passed is True


def test_confirm_cancel_consistent_and_skips_tool(tmp_path: Path, monkeypatch) -> None:
    report = _run_single_case(
        tmp_path,
        monkeypatch,
        SafetyRegressionCase(
            case_id="confirm_cancel_eval",
            case_type="confirm",
            pending_action_seed={"action": "change_address", "confirm": False},
            expected_manual_status="CANCELLED",
            expected_workflow_status="CANCELLED",
            expected_tool_calls_manual=0,
            expected_tool_calls_workflow=0,
            must_not_call_tool=True,
        ),
    )

    assert report.results[0].passed is True


def test_confirm_missing_pending_action_consistent_without_tool(
    tmp_path: Path,
    monkeypatch,
) -> None:
    report = _run_single_case(
        tmp_path,
        monkeypatch,
        SafetyRegressionCase(
            case_id="confirm_missing_eval",
            case_type="confirm",
            pending_action_seed={"missing": True},
            expected_manual_status="HTTP_400",
            expected_workflow_status="HTTP_400",
            expected_tool_calls_manual=0,
            expected_tool_calls_workflow=0,
            must_not_call_tool=True,
            must_write_trace=False,
        ),
    )

    assert report.results[0].passed is True


def test_confirm_policy_recheck_allow_consistent_and_calls_tool(
    tmp_path: Path,
    monkeypatch,
) -> None:
    report = _run_single_case(
        tmp_path,
        monkeypatch,
        SafetyRegressionCase(
            case_id="confirm_recheck_allow_eval",
            case_type="confirm",
            pending_action_seed={"action": "query_order", "order_id": "O10086"},
            expected_manual_status="EXECUTED",
            expected_workflow_status="EXECUTED",
            expected_tool_calls_manual=1,
            expected_tool_calls_workflow=1,
        ),
    )

    assert report.results[0].passed is True


def test_confirm_recheck_confirm_required_is_intentional_difference(
    tmp_path: Path,
    monkeypatch,
) -> None:
    report = _run_single_case(
        tmp_path,
        monkeypatch,
        SafetyRegressionCase(
            case_id="confirm_recheck_confirm_required_eval",
            case_type="confirm",
            pending_action_seed={"action": "change_address", "order_id": "O10086"},
            expected_manual_status="EXECUTED",
            expected_workflow_status="HUMAN_REQUIRED",
            expected_tool_calls_manual=1,
            expected_tool_calls_workflow=0,
            intentional_difference=True,
            difference_reason=(
                "workflow confirm 对二次复核仍需确认的场景采取更保守策略："
                "转人工，不执行工具。"
            ),
        ),
    )

    result = report.results[0]
    assert result.passed is True
    assert result.intentional_difference is True
    assert report.intentional_differences == 1
    assert report.failed_cases == 0


def test_intentional_difference_without_reason_counts_as_failed() -> None:
    case = SafetyRegressionCase(
        case_id="intentional_difference_missing_reason",
        case_type="confirm",
        expected_manual_status="EXECUTED",
        expected_workflow_status="HUMAN_REQUIRED",
        intentional_difference=True,
        difference_reason=None,
    )

    def fake_executor(case, mode):
        return SafetyRegressionObservation(
            mode=mode,
            status="EXECUTED" if mode == "manual" else "HUMAN_REQUIRED",
            tool_call_count=1 if mode == "manual" else 0,
            pending_action_count=1,
            trace_count=1,
        )

    report = run_safety_regression_cases([case], fake_executor)
    result = report.results[0]

    assert result.passed is False
    assert result.intentional_difference is True
    assert report.intentional_differences == 1
    assert report.failed_cases == 1
    assert "缺少 difference_reason" in result.failure_reason


def test_intentional_difference_with_unexpected_result_counts_as_failed() -> None:
    case = SafetyRegressionCase(
        case_id="intentional_difference_unexpected_tool_count",
        case_type="confirm",
        expected_manual_status="EXECUTED",
        expected_workflow_status="HUMAN_REQUIRED",
        expected_tool_calls_manual=1,
        expected_tool_calls_workflow=0,
        intentional_difference=True,
        difference_reason="workflow confirm 转人工，不执行工具。",
    )

    def fake_executor(case, mode):
        return SafetyRegressionObservation(
            mode=mode,
            status="EXECUTED" if mode == "manual" else "HUMAN_REQUIRED",
            tool_call_count=1,
            pending_action_count=1,
            trace_count=1,
        )

    report = run_safety_regression_cases([case], fake_executor)
    result = report.results[0]

    assert result.passed is False
    assert result.intentional_difference is True
    assert report.intentional_differences == 1
    assert report.failed_cases == 1
    assert "workflow_tool_call_count" in result.failure_reason


def test_unmarked_difference_is_reported_as_failed() -> None:
    case = SafetyRegressionCase(
        case_id="unmarked_difference",
        case_type="chat",
        expected_manual_status="SUCCESS",
        expected_workflow_status="DENY",
    )

    def fake_executor(case, mode):
        return SafetyRegressionObservation(
            mode=mode,
            status="SUCCESS" if mode == "manual" else "DENY",
            tool_call_count=1 if mode == "manual" else 0,
            pending_action_count=0,
            trace_count=1,
        )

    report = run_safety_regression_cases([case], fake_executor)
    result = report.results[0]

    assert result.passed is False
    assert report.failed_cases == 1
    assert "未标记行为差异" in result.failure_reason


def test_report_outputs_json_safe_dict(tmp_path: Path, monkeypatch) -> None:
    report = SafetyRegressionRunner(
        cases=build_default_safety_regression_cases()[:2],
        executor=SafetyApiExecutor(tmp_path, monkeypatch),
    ).run()
    payload = report.to_dict()

    assert payload["total_cases"] == 2
    assert payload["failed_cases"] == 0
    assert isinstance(payload["results"], list)
    assert {"case_id", "passed", "intentional_difference"}.issubset(
        payload["results"][0].keys()
    )
