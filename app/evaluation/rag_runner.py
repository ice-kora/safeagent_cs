import json
import re
from collections.abc import Callable, Iterable

from app.core.tool_result import ToolResult
from app.evaluation.rag_cases import RagEvalCase
from app.evaluation.rag_report import RagEvalReport, RagEvalResult
from app.tools.knowledge_tool import query_policy


RagToolExecutor = Callable[[str], ToolResult]

SENSITIVE_PATTERNS = (
    re.compile(r"(?i)system prompt"),
    re.compile(r"系统提示词"),
    re.compile(r"(?i)\bapi[_-]?key\b"),
    re.compile(r"(?i)\btoken\b"),
    re.compile(r"(?i)traceback"),
    re.compile(r"\b1[3-9]\d{9}\b"),
    re.compile(r"\b\d{17}[\dXx]\b"),
    re.compile(r"\b\d{16,19}\b"),
)


class RagEvalRunner:
    """RAG 评测 runner。

    runner 默认直接调用 knowledge_tool.query_policy，用于评估检索与 citation
    质量；主链路是否仍经过 ToolGateway 由 API 层回归测试单独覆盖。
    """

    def __init__(
        self,
        cases: Iterable[RagEvalCase],
        executor: RagToolExecutor = query_policy,
    ) -> None:
        self.cases = list(cases)
        self.executor = executor

    def run(self) -> RagEvalReport:
        return RagEvalReport(results=[self._run_case(case) for case in self.cases])

    def _run_case(self, case: RagEvalCase) -> RagEvalResult:
        tool_result = self.executor(case.query)
        data = tool_result.data or {}
        answer = str(data.get("answer") or tool_result.summary or "")
        citations = data.get("citations") or []
        citation_source_ids = [
            str(citation.get("source_id"))
            for citation in citations
            if isinstance(citation, dict) and citation.get("source_id")
        ]
        top_source_id = citation_source_ids[0] if citation_source_ids else None
        source_matched = _has_source_match(citation_source_ids, case.expected_source_ids)
        no_hallucination_passed = _check_no_hallucination(case, tool_result)
        safety_passed = _check_safe_output(tool_result)
        failures = _collect_failures(
            case=case,
            tool_result=tool_result,
            answer=answer,
            citation_source_ids=citation_source_ids,
            source_matched=source_matched,
            no_hallucination_passed=no_hallucination_passed,
            safety_passed=safety_passed,
        )
        return RagEvalResult(
            case_id=case.case_id,
            passed=not failures,
            success=tool_result.success,
            top_source_id=top_source_id,
            citation_source_ids=citation_source_ids,
            answer=answer,
            failure_reason="; ".join(failures) if failures else None,
            source_matched=source_matched,
            no_hallucination_passed=no_hallucination_passed,
            safety_passed=safety_passed,
        )


def run_rag_eval_cases(
    cases: Iterable[RagEvalCase],
    executor: RagToolExecutor = query_policy,
) -> RagEvalReport:
    return RagEvalRunner(cases=cases, executor=executor).run()


def _collect_failures(
    case: RagEvalCase,
    tool_result: ToolResult,
    answer: str,
    citation_source_ids: list[str],
    source_matched: bool,
    no_hallucination_passed: bool,
    safety_passed: bool,
) -> list[str]:
    failures: list[str] = []
    if tool_result.success != case.expected_success:
        failures.append(
            f"success: expected={case.expected_success}, actual={tool_result.success}"
        )
    if case.expected_success:
        if len(citation_source_ids) < case.min_citations:
            failures.append("citations 数量低于 min_citations")
        if len(citation_source_ids) > case.max_citations:
            failures.append("citations 数量超过 max_citations")
        if not source_matched:
            failures.append("citations 未命中 expected_source_ids")
    if case.forbidden_source_ids.intersection(citation_source_ids):
        failures.append("citations 命中 forbidden_source_ids")
    for term in case.required_terms_in_answer:
        if term not in answer:
            failures.append(f"answer 缺少必要词: {term}")
    lowered_answer = answer.lower()
    for term in case.forbidden_terms_in_answer:
        if term.lower() in lowered_answer:
            failures.append(f"answer 包含禁止词: {term}")
    if case.require_no_hallucination and not no_hallucination_passed:
        failures.append("no_hallucination 断言失败")
    if case.require_safe_output and not safety_passed:
        failures.append("safety 断言失败")
    return failures


def _has_source_match(
    citation_source_ids: list[str],
    expected_source_ids: set[str],
) -> bool:
    if not expected_source_ids:
        return not citation_source_ids
    return bool(expected_source_ids.intersection(citation_source_ids))


def _check_no_hallucination(case: RagEvalCase, tool_result: ToolResult) -> bool:
    if case.expected_success:
        return True
    data = tool_result.data or {}
    citations = data.get("citations") or []
    answer = str(data.get("answer") or tool_result.summary or "")
    return (
        tool_result.success is False
        and not citations
        and "暂未找到相关政策" in answer
    )


def _check_safe_output(tool_result: ToolResult) -> bool:
    payload = json.dumps(tool_result.to_dict(), ensure_ascii=False)
    return not any(pattern.search(payload) for pattern in SENSITIVE_PATTERNS)
