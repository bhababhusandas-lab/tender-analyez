"""Deterministic evaluation for the QA Reviewer agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.evals.bid_manager import CheckResult, _find_unnegated_claims, _fraction, _normalise
from app.evals.technical_expert import _table_row_count

SCORER_VERSION = "1.0.0"


@dataclass(frozen=True)
class QAEvaluationResult:
    case_id: str
    score: float
    passed: bool
    checks: tuple[CheckResult, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "score": round(self.score, 2),
            "passed": self.passed,
            "checks": [
                {"name": c.name, "score": round(c.score, 2), "weight": c.weight, "detail": c.detail}
                for c in self.checks
            ],
        }


def evaluate_qa_response(case: dict[str, Any], response: str, pass_threshold: float = 80.0) -> QAEvaluationResult:
    expected = case["expected"]
    normalised = _normalise(response)
    checks: list[CheckResult] = []

    def phrase_check(name: str, values: list[str], weight: float) -> None:
        hits = sum(_normalise(value) in normalised for value in values)
        checks.append(CheckResult(name, _fraction(hits, len(values)), weight, f"found {hits}/{len(values)}"))

    phrase_check("required_sections", expected["required_sections"], 20)
    phrase_check("requirement_coverage", expected["must_mention"], 20)
    phrase_check("numeric_facts", expected["numeric_facts"], 10)
    phrase_check("blocking_findings", expected["blocking_findings"], 15)

    rows = _table_row_count(response)
    minimum_rows = expected["minimum_checklist_rows"]
    checks.append(CheckResult("checklist_rows", min(rows / minimum_rows, 1.0), 15, f"found {rows}/{minimum_rows}"))

    verdict_ok = "no-go" in normalised or "no go" in normalised
    checks.append(CheckResult("submission_verdict", float(verdict_ok), 10, "explicit NO-GO required"))

    forbidden_hits = _find_unnegated_claims(response, expected["must_not_claim"])
    checks.append(CheckResult("hallucination_guard", float(not forbidden_hits), 10, "no invented requirements" if not forbidden_hits else f"found: {', '.join(forbidden_hits)}"))

    total = sum(c.weight for c in checks)
    score = 100 * sum(c.score * c.weight for c in checks) / total
    return QAEvaluationResult(case["id"], score, score >= pass_threshold, tuple(checks))
