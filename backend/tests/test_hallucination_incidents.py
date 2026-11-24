import json
from pathlib import Path

from app.core.analysis_quality import audit_final_report


DATASET = Path(__file__).resolve().parents[1] / "training" / "hallucination_incidents.jsonl"


def _cases():
    return [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_real_report_failures_remain_blocked():
    cases = _cases()
    assert len(cases) >= 12
    for case in cases:
        issues = audit_final_report(case["bad_report"], case["tender_text"], case["canonical_facts"])
        codes = {issue.code for issue in issues}
        assert set(case["expected_issue_codes"]).issubset(codes), case["id"]
