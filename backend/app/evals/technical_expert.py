"""Deterministic evaluation for the Technical Expert agent."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.evals.bid_manager import CheckResult, _find_unnegated_claims, _fraction, _normalise


SCORER_VERSION = "1.1.0"


@dataclass(frozen=True)
class TechnicalEvaluationResult:
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


def _table_row_count(response: str) -> int:
    rows = 0
    for line in response.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        if re.fullmatch(r"[|:\-\s]+", stripped):
            continue
        if "requirement" in stripped.casefold() and "status" in stripped.casefold():
            continue
        rows += 1
    return rows


def _methodology_paragraph_count(response: str) -> int:
    match = re.search(
        r"##\s*methodology\s*(.*?)(?=\n\s*##\s|\Z)", response, flags=re.IGNORECASE | re.DOTALL
    )
    if not match:
        return 0
    blocks = re.split(r"\n\s*\n", match.group(1).strip())
    return sum(len(re.sub(r"^[#*\-\d.\s]+", "", block).split()) >= 20 for block in blocks)


def evaluate_technical_response(
    case: dict[str, Any], response: str, pass_threshold: float = 80.0
) -> TechnicalEvaluationResult:
    expected = case["expected"]
    normalised = _normalise(response)
    checks: list[CheckResult] = []

    sections = [_normalise(value) for value in expected["required_sections"]]
    section_hits = sum(value in normalised for value in sections)
    checks.append(CheckResult("required_sections", _fraction(section_hits, len(sections)), 20, f"found {section_hits}/{len(sections)}"))

    mentions = [_normalise(value) for value in expected["must_mention"]]
    mention_hits = sum(value in normalised for value in mentions)
    checks.append(CheckResult("grounded_requirements", _fraction(mention_hits, len(mentions)), 25, f"found {mention_hits}/{len(mentions)}"))

    numbers = [_normalise(value) for value in expected["numeric_facts"]]
    number_hits = sum(value in normalised for value in numbers)
    checks.append(CheckResult("numeric_facts", _fraction(number_hits, len(numbers)), 15, f"found {number_hits}/{len(numbers)}"))

    minimum_rows = expected["minimum_compliance_rows"]
    row_count = _table_row_count(response)
    checks.append(CheckResult("compliance_rows", min(row_count / minimum_rows, 1.0), 15, f"found {row_count}/{minimum_rows}"))

    minimum_paragraphs = expected["minimum_methodology_paragraphs"]
    paragraph_count = _methodology_paragraph_count(response)
    checks.append(CheckResult("methodology_depth", min(paragraph_count / minimum_paragraphs, 1.0), 10, f"found {paragraph_count}/{minimum_paragraphs}"))

    forbidden_hits = _find_unnegated_claims(response, expected["must_not_claim"])
    checks.append(CheckResult("hallucination_guard", float(not forbidden_hits), 10, "no forbidden claims" if not forbidden_hits else f"found: {', '.join(forbidden_hits)}"))

    uncertainty_ok = (not expected["require_uncertainty_label"]) or "not specified in tender" in normalised
    checks.append(CheckResult("uncertainty_label", float(uncertainty_ok), 5, "required" if expected["require_uncertainty_label"] else "not required"))

    total_weight = sum(check.weight for check in checks)
    score = 100 * sum(check.score * check.weight for check in checks) / total_weight
    return TechnicalEvaluationResult(case["id"], score, score >= pass_threshold, tuple(checks))
