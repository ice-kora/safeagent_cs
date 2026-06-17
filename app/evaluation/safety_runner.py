from collections.abc import Callable, Iterable

from app.evaluation.safety_cases import SafetyRegressionCase
from app.evaluation.safety_report import (
    SafetyRegressionObservation,
    SafetyRegressionReport,
    SafetyRegressionResult,
)


SafetyCaseExecutor = Callable[
    [SafetyRegressionCase, str],
    SafetyRegressionObservation,
]


class SafetyRegressionRunner:
    """manual/workflow 双轨安全回归 runner。

    runner 不直接依赖 FastAPI 或 SQLite。它只负责执行 case、比较观测结果、
    识别 intentional difference，并生成 JSON-safe 报告。
    """

    def __init__(
        self,
        cases: Iterable[SafetyRegressionCase],
        executor: SafetyCaseExecutor,
    ) -> None:
        self.cases = list(cases)
        self.executor = executor

    def run(self) -> SafetyRegressionReport:
        results = [self._run_case(case) for case in self.cases]
        return SafetyRegressionReport(results=results)

    def _run_case(self, case: SafetyRegressionCase) -> SafetyRegressionResult:
        manual = self.executor(case, "manual")
        workflow = self.executor(case, "workflow")
        failure_reasons = self._collect_failures(case, manual, workflow)
        has_behavior_difference = self._has_behavior_difference(manual, workflow)
        if has_behavior_difference and not case.intentional_difference:
            failure_reasons.append("manual 与 workflow 存在未标记行为差异")
        if case.intentional_difference and not case.difference_reason:
            failure_reasons.append("intentional difference 缺少 difference_reason")

        passed = len(failure_reasons) == 0
        return SafetyRegressionResult(
            case_id=case.case_id,
            manual_status=manual.status,
            workflow_status=workflow.status,
            manual_tool_call_count=manual.tool_call_count,
            workflow_tool_call_count=workflow.tool_call_count,
            manual_pending_action_count=manual.pending_action_count,
            workflow_pending_action_count=workflow.pending_action_count,
            manual_trace_count=manual.trace_count,
            workflow_trace_count=workflow.trace_count,
            passed=passed,
            intentional_difference=case.intentional_difference,
            difference_reason=case.difference_reason,
            failure_reason="; ".join(failure_reasons) if failure_reasons else None,
        )

    def _collect_failures(
        self,
        case: SafetyRegressionCase,
        manual: SafetyRegressionObservation,
        workflow: SafetyRegressionObservation,
    ) -> list[str]:
        failures: list[str] = []
        self._check_expected(
            failures,
            "manual_status",
            manual.status,
            case.expected_manual_status,
        )
        self._check_expected(
            failures,
            "workflow_status",
            workflow.status,
            case.expected_workflow_status,
        )
        self._check_expected(
            failures,
            "manual_tool_call_count",
            manual.tool_call_count,
            case.expected_tool_calls_manual,
        )
        self._check_expected(
            failures,
            "workflow_tool_call_count",
            workflow.tool_call_count,
            case.expected_tool_calls_workflow,
        )
        self._check_expected(
            failures,
            "manual_pending_action_count",
            manual.pending_action_count,
            case.expected_pending_actions_manual,
        )
        self._check_expected(
            failures,
            "workflow_pending_action_count",
            workflow.pending_action_count,
            case.expected_pending_actions_workflow,
        )
        if case.must_not_call_tool and (
            manual.tool_call_count != 0 or workflow.tool_call_count != 0
        ):
            failures.append("must_not_call_tool 断言失败")
        if case.must_create_pending_action and (
            manual.pending_action_count < 1 or workflow.pending_action_count < 1
        ):
            failures.append("must_create_pending_action 断言失败")
        if case.must_write_trace and (
            manual.trace_count < 1 or workflow.trace_count < 1
        ):
            failures.append("must_write_trace 断言失败")
        return failures

    @staticmethod
    def _check_expected(
        failures: list[str],
        field_name: str,
        actual,
        expected,
    ) -> None:
        if expected is not None and actual != expected:
            failures.append(f"{field_name}: expected={expected}, actual={actual}")

    @staticmethod
    def _has_behavior_difference(
        manual: SafetyRegressionObservation,
        workflow: SafetyRegressionObservation,
    ) -> bool:
        return any(
            (
                manual.status != workflow.status,
                manual.tool_call_count != workflow.tool_call_count,
                manual.pending_action_count != workflow.pending_action_count,
            )
        )


def run_safety_regression_cases(
    cases: Iterable[SafetyRegressionCase],
    executor: SafetyCaseExecutor,
) -> SafetyRegressionReport:
    return SafetyRegressionRunner(cases=cases, executor=executor).run()

