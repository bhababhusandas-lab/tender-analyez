"""Deterministic evaluation for the Technical Writer agent."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.evals.bid_manager import CheckResult, _find_unnegated_claims, _fraction, _normalise
from app.evals.technical_expert import _table_row_count

SCORER_VERSION = "1.0.0"


@dataclass(frozen=True)
class WriterEvaluationResult:
    case_id: str
    score: float
    passed: bool
    checks: tuple[CheckResult, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"case_id": self.case_id, "score": round(self.score, 2), "passed": self.passed, "checks": [{"name": c.name, "score": round(c.score, 2), "weight": c.weight, "detail": c.detail} for c in self.checks]}


def _section_word_count(response: str, heading: str) -> int:
    match = re.search(rf"(?ims)^##\s*{re.escape(heading)}\s*$\s*(.*?)(?=^##\s|\Z)", response)
    return len(re.findall(r"\b[\w₹%-]+\b", match.group(1))) if match else 0


def evaluate_writer_response(case: dict[str, Any], response: str, pass_threshold: float = 80.0) -> WriterEvaluationResult:
    expected = case["expected"]
    normalised = _normalise(response)
    checks: list[CheckResult] = []

    def phrase_check(name: str, values: list[str], weight: float) -> None:
        hits = sum(_normalise(value) in normalised for value in values)
        checks.append(CheckResult(name, _fraction(hits, len(values)), weight, f"found {hits}/{len(values)}"))

    phrase_check("required_sections", expected["required_sections"], 20)
    phrase_check("content_coverage", expected["must_mention"], 15)
    phrase_check("fact_coverage", expected["facts"], 15)
    phrase_check("production_controls", expected["production_controls"], 15)

    rows = _table_row_count(response)
    minimum_rows = expected["minimum_mapping_rows"]
    checks.append(CheckResult("mapping_rows", min(rows / minimum_rows, 1.0), 15, f"found {rows}/{minimum_rows}"))

    words = _section_word_count(response, "Executive summary")
    summary_ok = 40 <= words <= expected["maximum_summary_words"]
    checks.append(CheckResult("summary_length", float(summary_ok), 10, f"found {words}/{expected['maximum_summary_words']} maximum words"))

    forbidden_hits = _find_unnegated_claims(response, expected["must_not_claim"])
    checks.append(CheckResult("hallucination_guard", float(not forbidden_hits), 10, "no invented proposal facts" if not forbidden_hits else f"found: {', '.join(forbidden_hits)}"))

    total = sum(c.weight for c in checks)
    score = 100 * sum(c.score * c.weight for c in checks) / total
    return WriterEvaluationResult(case["id"], score, score >= pass_threshold, tuple(checks))
