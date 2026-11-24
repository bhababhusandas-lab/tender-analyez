#!/usr/bin/env python3
"""Evaluate saved or live Legal & Compliance responses."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.agents.registry import get_system_prompt  # noqa: E402
from app.core.llm.claude_client import chat  # noqa: E402
from app.evals.bid_manager import load_cases  # noqa: E402
from app.evals.legal_compliance import SCORER_VERSION, evaluate_legal_response  # noqa: E402

DATASET = BACKEND_DIR / "training" / "legal_compliance" / "dataset.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--responses", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--response-output", type=Path)
    parser.add_argument("--threshold", type=float, default=80.0)
    args = parser.parse_args()
    if args.live and args.responses:
        parser.error("use either --live or --responses")

    cases = load_cases(args.dataset)
    if args.responses:
        responses = {item["id"]: item["response"] for item in (json.loads(line) for line in args.responses.read_text(encoding="utf-8").splitlines() if line.strip())}
    elif args.live:
        system = get_system_prompt("legal-compliance")
        responses = {}
        for case in cases:
            prompt = f"Review only the supplied facts.\n\nTENDER\n{case['input']['tender_text']}\n\nCOMPANY POSITION\n{case['input']['company_profile']}"
            responses[case["id"]] = chat(system_prompt=system, messages=[{"role": "user", "content": prompt}], agent_id="legal-compliance")
    else:
        responses = {case["id"]: case["reference_answer"] for case in cases}

    if args.response_output:
        with args.response_output.open("w", encoding="utf-8") as destination:
            for case in cases:
                destination.write(json.dumps({"id": case["id"], "response": responses[case["id"]]}, ensure_ascii=False) + "\n")

    results = [evaluate_legal_response(case, responses[case["id"]], args.threshold) for case in cases]
    report = {"agent": "legal-compliance", "scorer_version": SCORER_VERSION, "case_count": len(results), "average_score": round(sum(r.score for r in results) / len(results), 2), "passed": all(r.passed for r in results), "results": [r.as_dict() for r in results]}
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

