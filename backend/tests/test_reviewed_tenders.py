"""Accuracy regression over human-reviewed tenders (see reviewed_tenders/README.md)."""
import json
from pathlib import Path

import pytest

from app.core.tender_condense import TENDER_CHAR_BUDGET, build_model_input, condense_tender_text
from app.core.tender_evidence import (
    _amount_rupees, _parse_date, _parse_time, canonical_fact_record, extract_tender_evidence, format_evidence_block,
)

ROOT = Path(__file__).parent / "reviewed_tenders"
TENDERS = sorted(path.parent.name for path in ROOT.glob("*/expected.json"))
MAX_TEXT_BYTES = 500_000


def _fact_problems(field: str, value: str, check: dict) -> list[str]:
    problems = []
    if "amount" in check and _amount_rupees(value) != check["amount"]:
        problems.append(f"{field}: expected Rs {check['amount']:,}, got {value!r}")
    if "date" in check and _parse_date(value) != check["date"]:
        problems.append(f"{field}: expected date {check['date']}, got {value!r}")
    if "time" in check and _parse_time(value) != check["time"]:
        problems.append(f"{field}: expected time {check['time']}, got {value!r}")
    if "equals" in check and value != check["equals"]:
        problems.append(f"{field}: expected {check['equals']!r}, got {value!r}")
    for needle in check.get("contains", []):
        if needle.casefold() not in value.casefold():
            problems.append(f"{field}: {needle!r} missing from {value!r}")
    return problems


def test_there_are_reviewed_tenders():
    assert len(TENDERS) >= 2


@pytest.mark.parametrize("tender", TENDERS)
def test_reviewed_tender(tender):
    folder = ROOT / tender
    text_file = folder / "tender.txt"
    assert text_file.stat().st_size <= MAX_TEXT_BYTES, "keep tender.txt under ~500 KB"
    raw = text_file.read_text()
    expected = json.loads((folder / "expected.json").read_text())

    evidence = extract_tender_evidence(raw)
    facts, conflicts = canonical_fact_record(evidence)
    block = format_evidence_block(evidence)
    problems: list[str] = []

    for field, check in expected.get("facts", {}).items():
        if field in conflicts:
            problems.append(f"{field}: conflicting candidates {[item.value for item in conflicts[field]]}")
        elif field not in facts:
            problems.append(f"{field}: not extracted")
        else:
            problems.extend(_fact_problems(field, facts[field].value, check))

    for field in expected.get("absent_fields", []):
        found = [item.value for item in evidence if item.field == field]
        if found:
            problems.append(f"{field}: must not be extracted, got {found}")

    for field, amounts in expected.get("forbidden_amounts", {}).items():
        for item in evidence:
            if item.field == field and _amount_rupees(item.value) in amounts:
                problems.append(f"{field}: forbidden amount {item.value!r} ({item.excerpt!r})")

    for needle in expected.get("forbidden_in_evidence_block", []):
        if needle in block:
            problems.append(f"evidence block contains forbidden text {needle!r}")

    for check in expected.get("model_input", []):
        budget = check.get("budget", TENDER_CHAR_BUDGET)
        if check.get("evidence", True):
            model_input = build_model_input(raw, block, budget)
        else:
            model_input = condense_tender_text(raw, budget)
        if len(model_input) > budget:
            problems.append(f"model input is {len(model_input):,} characters, over the {budget:,} budget")
        for needle in check.get("contains", []):
            if needle not in model_input:
                problems.append(f"model input (budget {budget:,}) lost {needle!r}")

    assert not problems, f"{expected.get('name', tender)}:\n- " + "\n- ".join(problems)
