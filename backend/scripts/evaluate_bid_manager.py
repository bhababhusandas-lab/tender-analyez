#!/usr/bin/env python3
"""Run the Bid Manager regression evaluation locally or against the live agent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.evals.bid_manager import (  # noqa: E402
    SCORER_VERSION,
    build_agent_prompt,
    evaluate_many,
    load_cases,
)


DEFAULT_DATASET = BACKEND_DIR / "training" / "bid_manager" / "dataset.jsonl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--responses",
        type=Path,
        help="JSONL with one {id, response} object per evaluation case",
    )
    source.add_argument(
        "--live",
        action="store_true",
        help="Call the configured live Bid Manager (may consume provider quota)",
    )
    parser.add_argument("--split", choices=("train", "validation", "test"))
    parser.add_argument(
        "--case",
        action="append",
        dest="case_ids",
        help="Evaluate one case id; repeat the flag to select multiple cases",
    )
    parser.add_argument("--limit", type=int, help="Evaluate only the first N selected cases")
    parser.add_argument("--threshold", type=float, default=80.0)
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    parser.add_argument(
        "--response-output",
        type=Path,
        help="Optional JSONL path for candidate responses (use only with approved data)",
    )
    return parser.parse_args()


def load_responses(path: Path) -> dict[str, str]:
    responses: dict[str, str] = {}
    with path.open(encoding="utf-8") as source:
        for line_number, raw_line in enumerate(source, start=1):
            if not raw_line.strip():
                continue
            item = json.loads(raw_line)
            if not isinstance(item.get("id"), str) or not isinstance(item.get("response"), str):
                raise ValueError(f"{path}:{line_number}: expected string id and response")
            responses[item["id"]] = item["response"]
    return responses


def live_responses(cases: list[dict]) -> dict[str, str]:
    from app.agents.registry import get_system_prompt
    from app.core.llm.claude_client import chat

    system_prompt = get_system_prompt("bid-manager")
    responses: dict[str, str] = {}
    for index, case in enumerate(cases, start=1):
        print(f"Running live case {index}/{len(cases)}: {case['id']}", file=sys.stderr)
        responses[case["id"]] = chat(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": build_agent_prompt(case)}],
            agent_id="bid-manager",
        )
    return responses


def main() -> int:
    args = parse_args()
    cases = load_cases(args.dataset)
    if args.split:
        cases = [case for case in cases if case["split"] == args.split]
    if args.case_ids:
        selected_ids = set(args.case_ids)
        cases = [case for case in cases if case["id"] in selected_ids]
    if args.limit is not None:
        cases = cases[: args.limit]
    if not cases:
        raise ValueError("no cases selected")

    if args.live:
        responses = live_responses(cases)
    elif args.responses:
        responses = load_responses(args.responses)
    else:
        responses = {case["id"]: case["reference_answer"] for case in cases}

    if args.response_output:
        args.response_output.parent.mkdir(parents=True, exist_ok=True)
        with args.response_output.open("w", encoding="utf-8") as destination:
            for case in cases:
                destination.write(
                    json.dumps(
                        {"id": case["id"], "response": responses[case["id"]]},
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    results = evaluate_many(cases, responses, args.threshold)
    report = {
        "agent": "bid-manager",
        "scorer_version": SCORER_VERSION,
        "dataset": str(args.dataset),
        "case_count": len(results),
        "pass_threshold": args.threshold,
        "average_score": round(sum(result.score for result in results) / len(results), 2),
        "passed": all(result.passed for result in results),
        "results": [result.as_dict() for result in results],
    }

    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
