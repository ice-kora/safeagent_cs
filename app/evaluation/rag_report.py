from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RagEvalResult:
    """单条 RAG 评测结果。"""

    case_id: str
    passed: bool
    success: bool
    top_source_id: str | None
    citation_source_ids: list[str]
    answer: str
    failure_reason: str | None
    source_matched: bool
    no_hallucination_passed: bool
    safety_passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "passed": self.passed,
            "success": self.success,
            "top_source_id": self.top_source_id,
            "citation_source_ids": self.citation_source_ids,
            "answer": self.answer,
            "failure_reason": self.failure_reason,
            "source_matched": self.source_matched,
            "no_hallucination_passed": self.no_hallucination_passed,
            "safety_passed": self.safety_passed,
        }


@dataclass(frozen=True)
class RagEvalReport:
    """RAG citation quality 回归报告。"""

    results: list[RagEvalResult]

    @property
    def total_cases(self) -> int:
        return len(self.results)

    @property
    def passed_cases(self) -> int:
        return sum(1 for result in self.results if result.passed)

    @property
    def failed_cases(self) -> int:
        return sum(1 for result in self.results if not result.passed)

    @property
    def source_accuracy(self) -> float:
        source_cases = [result for result in self.results if result.success]
        if not source_cases:
            return 1.0
        return _rate(result.source_matched for result in source_cases)

    @property
    def no_hallucination_pass_rate(self) -> float:
        no_match_cases = [
            result
            for result in self.results
            if not result.success or not result.citation_source_ids
        ]
        if not no_match_cases:
            return 1.0
        return _rate(result.no_hallucination_passed for result in no_match_cases)

    @property
    def safety_pass_rate(self) -> float:
        if not self.results:
            return 1.0
        return _rate(result.safety_passed for result in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "source_accuracy": self.source_accuracy,
            "no_hallucination_pass_rate": self.no_hallucination_pass_rate,
            "safety_pass_rate": self.safety_pass_rate,
            "results": [result.to_dict() for result in self.results],
        }


def _rate(values) -> float:
    values = list(values)
    if not values:
        return 1.0
    return sum(1 for value in values if value) / len(values)
