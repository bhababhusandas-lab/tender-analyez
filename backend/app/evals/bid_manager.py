"""Deterministic baseline evaluation for the Bid Manager agent.

This scorer intentionally checks facts and structure that can be verified
without asking another model to judge the answer.  It is a fast regression
gate, not a replacement for procurement-expert review.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ALLOWED_DECISIONS = {"BID", "NO-BID", "CONDITIONAL"}
ALLOWED_SPLITS = {"train", "validation", "test"}
SCORER_VERSION = "1.5.0"

_NUMBER_WORDS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    score: float
    weight: float
    detail: str


@dataclass(frozen=True)
class EvaluationResult:
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
                {
                    "name": check.name,
                    "score": round(check.score, 2),
                    "weight": check.weight,
                    "detail": check.detail,
                }
                for check in self.checks
            ],
        }


def _normalise(text: str) -> str:
    dash_normalised = text.translate(str.maketrans({"‐": "-", "‑": "-", "–": "-", "—": "-"}))
    normalised = re.sub(r"\s+", " ", dash_normalised.casefold()).strip()
    normalised = re.sub(r"\s+%", "%", normalised)
    normalised = re.sub(r"₹\s+", "₹", normalised)
    normalised = re.sub(r"(?<=\w)-(?=\w)", " ", normalised)
    normalised = re.sub(r"(?<=\d)\s*cr\b", " crore", normalised)
    for word, digit in _NUMBER_WORDS.items():
        normalised = re.sub(rf"\b{word}\b", digit, normalised)
    normalised = re.sub(r"\b(\d+)\s+(years|months|days|weeks)\b", lambda m: f"{m.group(1)} {m.group(2)[:-1]}", normalised)
    return normalised


def _opening_decision(response: str) -> str | None:
    """Read the verdict at the start of the Decision section.

    A later phrase such as "conditional gate" must not rescue a contradictory
    opening BID verdict.
    """
    match = re.search(
        r"(?:^|\n)\s*##\s*decision\s*\n+\s*(?:\*\*|__)?\s*([^\n]+)",
        response,
        flags=re.IGNORECASE,
    )
    opening = _normalise(match.group(1) if match else response[:160])
    opening = re.sub(r"^(?:decision|recommendation|verdict)\s*[:\-]\s*", "", opening)
    opening = opening.lstrip("*_ ")
    if re.match(r"no[\s-]?bid\b", opening):
        return "NO-BID"
    if re.match(r"conditional(?:ly)?(?:\s+bid|\s+go)?\b", opening):
        return "CONDITIONAL"
    if re.match(r"bid\b", opening):
        return "BID"
    return None


def _fraction(found: int, total: int) -> float:
    return 1.0 if total == 0 else found / total


def _find_unnegated_claims(text: str, forbidden: list[str]) -> list[str]:
    """Return forbidden phrases that are asserted rather than directly negated."""
    normalised = _normalise(text)
    hits: list[str] = []
    for raw_phrase in forbidden:
        phrase = _normalise(raw_phrase)
        for match in re.finditer(re.escape(phrase), normalised):
            prefix = normalised[max(0, match.start() - 24):match.start()]
            if re.search(r"\b(?:no|not|never|without|missing)\s+$", prefix):
                continue
            wider_prefix = normalised[max(0, match.start() - 100):match.start()]
            if re.search(r"\b(?:do not|don't|never)\s+(?:invent|claim|assume|state|assert)\b.{0,80}$", wider_prefix):
                continue
            suffix = normalised[match.end():match.end() + 120]
            if re.match(r".{0,90}\b(?:is|are|was|were)?\s*(?:not specified|not found|unknown|absent)\b", suffix):
                continue
            hits.append(phrase)
            break
    return hits


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    with path.open(encoding="utf-8") as source:
        for line_number, raw_line in enumerate(source, start=1):
            if not raw_line.strip():
                continue
            try:
                case = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc

            case_id = case.get("id")
            split = case.get("split")
            expected = case.get("expected", {})
            decision = expected.get("decision")
            if not isinstance(case_id, str) or not case_id:
                raise ValueError(f"{path}:{line_number}: missing non-empty id")
            if case_id in seen_ids:
                raise ValueError(f"{path}:{line_number}: duplicate id {case_id!r}")
            if split not in ALLOWED_SPLITS:
                raise ValueError(f"{path}:{line_number}: invalid split {split!r}")
            if decision not in ALLOWED_DECISIONS:
                raise ValueError(f"{path}:{line_number}: invalid decision {decision!r}")
            if not isinstance(case.get("input"), dict):
                raise ValueError(f"{path}:{line_number}: input must be an object")
            if not isinstance(case.get("reference_answer"), str):
                raise ValueError(f"{path}:{line_number}: reference_answer must be a string")

            seen_ids.add(case_id)
            cases.append(case)

    if not cases:
        raise ValueError(f"{path}: dataset is empty")
    return cases


def build_agent_prompt(case: dict[str, Any]) -> str:
    payload = case["input"]
    return (
        "Analyse this tender as the Bid Manager. Use only the supplied tender "
        "and company facts. Give a clear BID, NO-BID, or CONDITIONAL decision; "
        "cite the decisive requirements; list deadlines and actions; and label "
        "missing information as 'Not specified in tender'.\n\n"
        f"TENDER\n{payload['tender_text']}\n\n"
        f"COMPANY PROFILE\n{payload['company_profile']}"
    )


def evaluate_response(
    case: dict[str, Any], response: str, pass_threshold: float = 80.0
) -> EvaluationResult:
    expected = case["expected"]
    normalised = _normalise(response)
    checks: list[CheckResult] = []

    decision = expected["decision"]
    opening_decision = _opening_decision(response)
    decision_ok = opening_decision == decision
    checks.append(
        CheckResult(
            "decision",
            float(decision_ok),
            25,
            f"expected {decision}; opening verdict {opening_decision or 'not found'}",
        )
    )

    sections = [_normalise(item) for item in expected.get("required_sections", [])]
    section_hits = sum(section in normalised for section in sections)
    checks.append(
        CheckResult(
            "required_sections",
            _fraction(section_hits, len(sections)),
            20,
            f"found {section_hits}/{len(sections)}",
        )
    )

    mentions = [_normalise(item) for item in expected.get("must_mention", [])]
    mention_hits = sum(item in normalised for item in mentions)
    checks.append(
        CheckResult(
            "grounded_requirements",
            _fraction(mention_hits, len(mentions)),
            25,
            f"found {mention_hits}/{len(mentions)} required facts",
        )
    )

    numeric_facts = [_normalise(item) for item in expected.get("numeric_facts", [])]
    numeric_hits = sum(item in normalised for item in numeric_facts)
    checks.append(
        CheckResult(
            "numeric_facts",
            _fraction(numeric_hits, len(numeric_facts)),
            15,
            f"found {numeric_hits}/{len(numeric_facts)}",
        )
    )

    forbidden_hits = _find_unnegated_claims(response, expected.get("must_not_claim", []))
    checks.append(
        CheckResult(
            "hallucination_guard",
            float(not forbidden_hits),
            10,
            "no forbidden claims" if not forbidden_hits else f"found: {', '.join(forbidden_hits)}",
        )
    )

    uncertainty_required = bool(expected.get("require_uncertainty_label", False))
    uncertainty_ok = (not uncertainty_required) or "not specified in tender" in normalised
    checks.append(
        CheckResult(
            "uncertainty_label",
            float(uncertainty_ok),
            5,
            "required" if uncertainty_required else "not required",
        )
    )

    total_weight = sum(check.weight for check in checks)
    score = 100 * sum(check.score * check.weight for check in checks) / total_weight
    return EvaluationResult(case["id"], score, score >= pass_threshold, tuple(checks))


def evaluate_many(
    cases: Iterable[dict[str, Any]],
    responses: dict[str, str],
    pass_threshold: float = 80.0,
) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    for case in cases:
        case_id = case["id"]
        if case_id not in responses:
            raise ValueError(f"missing response for case {case_id!r}")
        results.append(evaluate_response(case, responses[case_id], pass_threshold))
    return results
