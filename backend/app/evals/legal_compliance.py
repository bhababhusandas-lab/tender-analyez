"""Deterministic evaluation for the Legal & Compliance agent."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.evals.bid_manager import CheckResult, _find_unnegated_claims, _fraction, _normalise
from app.evals.technical_expert import _table_row_count

SCORER_VERSION = "1.2.0"


@dataclass(frozen=True)
class LegalEvaluationResult:
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


def _prebid_query_count(response: str) -> int:
    match = re.search(r"##\s*pre[-‐‑–—]bid queries\s*(.*?)(?=\n\s*##\s|\Z)", response, re.I | re.S)
    if not match:
        return 0
    body = match.group(1)
    numbered = len(re.findall(r"(?m)^\s*\d+[.)]\s+", body))
    return max(numbered, body.count("?"))


def evaluate_legal_response(case: dict[str, Any], response: str, pass_threshold: float = 80.0) -> LegalEvaluationResult:
    expected = case["expected"]
    normalised = _normalise(response)
    checks: list[CheckResult] = []

    sections = [_normalise(value) for value in expected["required_sections"]]
    section_hits = sum(value in normalised for value in sections)
    checks.append(CheckResult("required_sections", _fraction(section_hits, len(sections)), 20, f"found {section_hits}/{len(sections)}"))

    mentions = [_normalise(value) for value in expected["must_mention"]]
    mention_hits = sum(value in normalised for value in mentions)
    checks.append(CheckResult("clause_coverage", _fraction(mention_hits, len(mentions)), 25, f"found {mention_hits}/{len(mentions)}"))

    numbers = [_normalise(value) for value in expected["numeric_facts"]]
    number_hits = sum(value in normalised for value in numbers)
    checks.append(CheckResult("numeric_exposure", _fraction(number_hits, len(numbers)), 15, f"found {number_hits}/{len(numbers)}"))

    row_count = _table_row_count(response)
    minimum_rows = expected["minimum_clause_rows"]
    checks.append(CheckResult("clause_rows", min(row_count / minimum_rows, 1.0), 15, f"found {row_count}/{minimum_rows}"))

    query_count = _prebid_query_count(response)
    minimum_queries = expected["minimum_prebid_queries"]
    checks.append(CheckResult("prebid_queries", min(query_count / minimum_queries, 1.0), 10, f"found {query_count}/{minimum_queries}"))

    forbidden_hits = _find_unnegated_claims(response, expected["must_not_claim"])
    checks.append(CheckResult("hallucination_guard", float(not forbidden_hits), 10, "no forbidden claims" if not forbidden_hits else f"found: {', '.join(forbidden_hits)}"))

    uncertainty_ok = (not expected["require_missing_clause_label"]) or "not found in tender" in normalised
    checks.append(CheckResult("missing_clause_label", float(uncertainty_ok), 5, "required" if expected["require_missing_clause_label"] else "not required"))

    total = sum(c.weight for c in checks)
    score = 100 * sum(c.score * c.weight for c in checks) / total
    return LegalEvaluationResult(case["id"], score, score >= pass_threshold, tuple(checks))
