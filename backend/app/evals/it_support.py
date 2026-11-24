"""Deterministic evaluation for the IT Support agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.evals.bid_manager import CheckResult, _find_unnegated_claims, _fraction, _normalise

SCORER_VERSION = "1.0.0"


@dataclass(frozen=True)
class ITSupportEvaluationResult:
    case_id: str
    score: float
    passed: bool
    checks: tuple[CheckResult, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"case_id": self.case_id, "score": round(self.score, 2), "passed": self.passed, "checks": [{"name": c.name, "score": round(c.score, 2), "weight": c.weight, "detail": c.detail} for c in self.checks]}


def evaluate_it_response(case: dict[str, Any], response: str, pass_threshold: float = 80.0) -> ITSupportEvaluationResult:
    expected = case["expected"]
    normalised = _normalise(response)
    checks: list[CheckResult] = []

    def phrase_check(name: str, values: list[str], weight: float) -> None:
        hits = sum(_normalise(value) in normalised for value in values)
        checks.append(CheckResult(name, _fraction(hits, len(values)), weight, f"found {hits}/{len(values)}"))

    phrase_check("required_sections", expected["required_sections"], 20)
    phrase_check("evidence_coverage", expected["must_mention"], 15)
    phrase_check("numeric_facts", expected["numeric_facts"], 10)
    phrase_check("recovery_steps", expected["recovery_steps"], 25)
    phrase_check("security_controls", expected["security_controls"], 15)

    forbidden_hits = _find_unnegated_claims(response, expected["must_not_claim"])
    checks.append(CheckResult("unsafe_claim_guard", float(not forbidden_hits), 10, "no unsafe or invented claims" if not forbidden_hits else f"found: {', '.join(forbidden_hits)}"))

    uncertainty_ok = "no evidence of a portal outage" in normalised or "portal outage is not verified" in normalised
    checks.append(CheckResult("outage_uncertainty", float(uncertainty_ok), 5, "outage must remain unverified"))

    total = sum(c.weight for c in checks)
    score = 100 * sum(c.score * c.weight for c in checks) / total
    return ITSupportEvaluationResult(case["id"], score, score >= pass_threshold, tuple(checks))
