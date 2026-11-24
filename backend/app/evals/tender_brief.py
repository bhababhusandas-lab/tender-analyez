"""Deterministic evaluation for the Tender Brief agent."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.evals.bid_manager import CheckResult, _find_unnegated_claims, _fraction, _normalise

SCORER_VERSION = "1.0.0"

BRIEF_SECTIONS = (
    "1. Tender Overview",
    "2. Key Dates & Schedule",
    "3. Eligibility Criteria",
    "4. Scope of Work / Deliverables",
    "5. Commercial Terms",
    "6. Evaluation Process",
    "7. Documents to be Submitted",
    "8. Appendices & Annexures",
    "9. Discrepancies to Clarify at Pre-bid",
)


@dataclass(frozen=True)
class BriefEvaluationResult:
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


def _level_two_sections(response: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in response.splitlines():
        heading = re.match(r"^\s*##\s+(.+?)\s*$", line)
        if heading:
            current = sections.setdefault(heading.group(1).replace("**", "").strip(), [])
        elif current is not None:
            current.append(line)
    return {title: "\n".join(body) for title, body in sections.items()}


def evaluate_brief_response(case: dict[str, Any], response: str, pass_threshold: float = 80.0) -> BriefEvaluationResult:
    expected = case["expected"]
    normalised = _normalise(response)
    sections = _level_two_sections(response)
    checks: list[CheckResult] = []

    in_order = [title for title in sections if title in BRIEF_SECTIONS]
    exact = sum(title in sections for title in BRIEF_SECTIONS)
    ordered = in_order == [title for title in BRIEF_SECTIONS if title in sections]
    checks.append(CheckResult("template_sections", _fraction(exact, len(BRIEF_SECTIONS)) * (1.0 if ordered else 0.5), 20,
                              f"found {exact}/{len(BRIEF_SECTIONS)} headings{'' if ordered else ', out of order'}"))

    def phrase_check(name: str, text: str, values: list[str], weight: float) -> None:
        body = _normalise(text)
        hits = sum(_normalise(value) in body for value in values)
        checks.append(CheckResult(name, _fraction(hits, len(values)), weight, f"found {hits}/{len(values)}"))

    phrase_check("numeric_facts", response, expected["numeric_facts"], 20)
    phrase_check("coverage", response, expected["must_mention"], 15)
    phrase_check("citations", response, expected["citations"], 10)
    discrepancies = sections.get(BRIEF_SECTIONS[-1], "")
    phrase_check("discrepancies_caught", discrepancies, expected["discrepancy_values"], 20)

    marker_ok = "not stated in the tender" in normalised
    checks.append(CheckResult("missing_info_marker", float(marker_ok), 5, "'Not stated in the tender' used for gaps"))

    forbidden_hits = _find_unnegated_claims(response, expected["must_not_claim"])
    checks.append(CheckResult("hallucination_guard", float(not forbidden_hits), 10,
                              "no invented facts" if not forbidden_hits else f"found: {', '.join(forbidden_hits)}"))

    total = sum(c.weight for c in checks)
    score = 100 * sum(c.score * c.weight for c in checks) / total
    return BriefEvaluationResult(case["id"], score, score >= pass_threshold, tuple(checks))
