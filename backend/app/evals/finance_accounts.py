"""Deterministic evaluation for the Finance & Accounts agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.evals.bid_manager import CheckResult, _find_unnegated_claims, _fraction, _normalise
from app.evals.technical_expert import _table_row_count

SCORER_VERSION = "1.3.0"

UNSUPPORTED_DEFAULTS = [
    "per standard government tender practice",
    "DD/BG/online as per tender",
    "no upward adjustment is permissible",
]


@dataclass(frozen=True)
class FinanceEvaluationResult:
    case_id: str
    score: float
    passed: bool
    checks: tuple[CheckResult, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"case_id": self.case_id, "score": round(self.score, 2), "passed": self.passed, "checks": [{"name": c.name, "score": round(c.score, 2), "weight": c.weight, "detail": c.detail} for c in self.checks]}


def evaluate_finance_response(case: dict[str, Any], response: str, pass_threshold: float = 80.0) -> FinanceEvaluationResult:
    expected = case["expected"]
    normalised = _normalise(response)
    checks: list[CheckResult] = []

    sections = [_normalise(v) for v in expected["required_sections"]]
    section_hits = sum(v in normalised for v in sections)
    checks.append(CheckResult("required_sections", _fraction(section_hits, len(sections)), 15, f"found {section_hits}/{len(sections)}"))

    mentions = [_normalise(v) for v in expected["must_mention"]]
    mention_hits = sum(v in normalised for v in mentions)
    checks.append(CheckResult("financial_coverage", _fraction(mention_hits, len(mentions)), 20, f"found {mention_hits}/{len(mentions)}"))

    facts = [_normalise(v) for v in expected["numeric_facts"]]
    fact_hits = sum(v in normalised for v in facts)
    checks.append(CheckResult("source_figures", _fraction(fact_hits, len(facts)), 15, f"found {fact_hits}/{len(facts)}"))

    calculations = [_normalise(v) for v in expected["required_calculations"]]
    rupee_table = "(₹)" in normalised or "amount ₹" in normalised or "cost ₹" in normalised
    calculation_hits = sum(
        value in normalised or (rupee_table and value.startswith("₹") and value[1:] in normalised)
        for value in calculations
    )
    checks.append(CheckResult("verified_calculations", _fraction(calculation_hits, len(calculations)), 25, f"found {calculation_hits}/{len(calculations)}"))

    minimum_rows = expected["minimum_boq_rows"]
    rows = _table_row_count(response)
    checks.append(CheckResult("boq_rows", min(rows / minimum_rows, 1.0), 10, f"found {rows}/{minimum_rows}"))

    forbidden_hits = _find_unnegated_claims(response, [*expected["must_not_claim"], *UNSUPPORTED_DEFAULTS])
    checks.append(CheckResult("hallucination_guard", float(not forbidden_hits), 10, "no forbidden claims" if not forbidden_hits else f"found: {', '.join(forbidden_hits)}"))

    uncertainty_ok = (
        not expected["require_uncertainty_label"]
        or "not specified in tender" in normalised
        or "not specified in the tender" in normalised
        or "specified in the tender" in normalised and "no price escalation" in normalised
    )
    checks.append(CheckResult("uncertainty_label", float(uncertainty_ok), 5, "required" if expected["require_uncertainty_label"] else "not required"))

    total = sum(c.weight for c in checks)
    score = 100 * sum(c.score * c.weight for c in checks) / total
    return FinanceEvaluationResult(case["id"], score, score >= pass_threshold, tuple(checks))
