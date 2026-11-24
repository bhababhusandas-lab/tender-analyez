"""Deterministic evaluation for the Market Intelligence agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.evals.bid_manager import CheckResult, _find_unnegated_claims, _fraction, _normalise
from app.evals.technical_expert import _table_row_count

SCORER_VERSION = "1.0.0"


@dataclass(frozen=True)
class MarketEvaluationResult:
    case_id: str
    score: float
    passed: bool
    checks: tuple[CheckResult, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"case_id": self.case_id, "score": round(self.score, 2), "passed": self.passed, "checks": [{"name": c.name, "score": round(c.score, 2), "weight": c.weight, "detail": c.detail} for c in self.checks]}


def evaluate_market_response(case: dict[str, Any], response: str, pass_threshold: float = 80.0) -> MarketEvaluationResult:
    expected = case["expected"]
    normalised = _normalise(response)
    checks: list[CheckResult] = []

    def phrase_check(name: str, values: list[str], weight: float) -> None:
        hits = sum(_normalise(value) in normalised for value in values)
        checks.append(CheckResult(name, _fraction(hits, len(values)), weight, f"found {hits}/{len(values)}"))

    phrase_check("required_sections", expected["required_sections"], 20)
    phrase_check("source_coverage", expected["sources"], 15)
    phrase_check("market_facts", expected["facts"], 20)
    phrase_check("competitor_coverage", expected["competitors"], 10)
    phrase_check("uncertainty_labels", expected["uncertainty_labels"], 10)

    rows = _table_row_count(response)
    minimum_rows = expected["minimum_rows"]
    checks.append(CheckResult("evidence_rows", min(rows / minimum_rows, 1.0), 10, f"found {rows}/{minimum_rows}"))

    forbidden_hits = _find_unnegated_claims(response, expected["must_not_claim"])
    checks.append(CheckResult("hallucination_guard", float(not forbidden_hits), 15, "no invented market claims" if not forbidden_hits else f"found: {', '.join(forbidden_hits)}"))

    total = sum(c.weight for c in checks)
    score = 100 * sum(c.score * c.weight for c in checks) / total
    return MarketEvaluationResult(case["id"], score, score >= pass_threshold, tuple(checks))
