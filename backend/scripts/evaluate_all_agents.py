#!/usr/bin/env python3
"""Run every locked specialist-agent evaluation and produce one fleet report."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.evals.bid_manager import load_cases  # noqa: E402


EVALUATORS = {
    "bid-manager": ("bid_manager", "evaluate_response"),
    "technical-expert": ("technical_expert", "evaluate_technical_response"),
    "finance-accounts": ("finance_accounts", "evaluate_finance_response"),
    "legal-compliance": ("legal_compliance", "evaluate_legal_response"),
    "doc-controller": ("doc_controller", "evaluate_document_response"),
    "admin-hr": ("admin_hr", "evaluate_hr_response"),
    "market-intelligence": ("market_intelligence", "evaluate_market_response"),
    "govt-relations": ("govt_relations", "evaluate_relations_response"),
    "technical-writer": ("technical_writer", "evaluate_writer_response"),
    "bid-pricing": ("bid_pricing", "evaluate_pricing_response"),
    "qa-reviewer": ("qa_reviewer", "evaluate_qa_response"),
    "it-support": ("it_support", "evaluate_it_response"),
    "tender-brief": ("tender_brief", "evaluate_brief_response"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--threshold", type=float, default=80.0)
    args = parser.parse_args()

    agents: list[dict] = []
    for agent_id, (module_name, function_name) in EVALUATORS.items():
        module = importlib.import_module(f"app.evals.{module_name}")
        evaluator = getattr(module, function_name)
        dataset = BACKEND_DIR / "training" / module_name / "dataset.jsonl"
        results = [evaluator(case, case["reference_answer"], args.threshold) for case in load_cases(dataset)]
        agents.append({
            "agent": agent_id,
            "scorer_version": module.SCORER_VERSION,
            "case_count": len(results),
            "average_score": round(sum(result.score for result in results) / len(results), 2),
            "passed": all(result.passed for result in results),
        })

    report = {
        "agent_count": len(agents),
        "case_count": sum(agent["case_count"] for agent in agents),
        "passed": all(agent["passed"] for agent in agents),
        "agents": agents,
    }
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
