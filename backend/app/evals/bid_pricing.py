"""Deterministic evaluation for the Bid Pricing agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.evals.bid_manager import CheckResult, _find_unnegated_claims, _fraction, _normalise
from app.evals.technical_expert import _table_row_count

SCORER_VERSION = "1.0.0"


@dataclass(frozen=True)
class PricingEvaluationResult:
    case_id: str
    score: float
    passed: bool
    checks: tuple[CheckResult, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"case_id": self.case_id, "score": round(self.score, 2), "passed": self.passed, "checks": [{"name": c.name, "score": round(c.score, 2), "weight": c.weight, "detail": c.detail} for c in self.checks]}


def evaluate_pricing_response(case: dict[str, Any], response: str, pass_threshold: float = 80.0) -> PricingEvaluationResult:
    expected = case["expected"]
    normalised = _normalise(response)
    checks: list[CheckResult] = []

    def phrase_check(name: str, values: list[str], weight: float) -> None:
        hits = sum(_normalise(value) in normalised for value in values)
        checks.append(CheckResult(name, _fraction(hits, len(values)), weight, f"found {hits}/{len(values)}"))

    phrase_check("required_sections", expected["required_sections"], 15)
    phrase_check("pricing_coverage", expected["must_mention"], 15)
    phrase_check("source_figures", expected["numeric_facts"], 15)
    phrase_check("verified_calculations", expected["required_calculations"], 25)

    rows = _table_row_count(response)
    minimum_rows = expected["minimum_scenario_rows"]
    checks.append(CheckResult("scenario_rows", min(rows / minimum_rows, 1.0), 10, f"found {rows}/{minimum_rows}"))

    forbidden_hits = _find_unnegated_claims(response, expected["must_not_claim"])
    checks.append(CheckResult("market_hallucination_guard", float(not forbidden_hits), 15, "no invented market claims" if not forbidden_hits else f"found: {', '.join(forbidden_hits)}"))

    evidence_ok = "no verified historical l1 data" in normalised or "historical l1 data is not provided" in normalised
    checks.append(CheckResult("market_evidence_label", float(evidence_ok), 5, "verified absence required"))

    total = sum(c.weight for c in checks)
    score = 100 * sum(c.score * c.weight for c in checks) / total
    return PricingEvaluationResult(case["id"], score, score >= pass_threshold, tuple(checks))

