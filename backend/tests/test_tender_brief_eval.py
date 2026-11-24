import unittest
from pathlib import Path

from app.agents.registry import AGENT_SYSTEM_PROMPTS, get_system_prompt
from app.api.v1.tender_analysis import PIPELINE_AGENTS
from app.core.llm.claude_client import tier_for
from app.evals.bid_manager import load_cases
from app.evals.tender_brief import BRIEF_SECTIONS, evaluate_brief_response

DATASET = Path(__file__).resolve().parents[1] / "training" / "tender_brief" / "dataset.jsonl"


class TenderBriefRegistrationTests(unittest.TestCase):
    def test_agent_runs_in_every_bid_pipeline(self):
        agent = next((a for a in PIPELINE_AGENTS if a["id"] == "tender-brief"), None)
        self.assertIsNotNone(agent)
        self.assertEqual(agent["name"], "Tender Brief AI")
        self.assertIn("Final Bid Recommendation", agent["prompt"])

    def test_agent_has_system_prompt_and_analysis_tier(self):
        self.assertIn("tender-brief", AGENT_SYSTEM_PROMPTS)
        self.assertEqual(tier_for("tender-brief"), "analysis")


class TenderBriefEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = load_cases(DATASET)[0]

    def test_reference_answer_passes(self):
        self.assertEqual(evaluate_brief_response(self.case, self.case["reference_answer"]).score, 100)

    def test_shallow_brief_fails(self):
        self.assertFalse(evaluate_brief_response(self.case, "## 1. Tender Overview\nHealth insurance tender.").passed)

    def test_missed_discrepancy_is_detected(self):
        response = self.case["reference_answer"].split("## 9.")[0] + "## 9. Discrepancies to Clarify at Pre-bid\nNone found\n"
        check = next(c for c in evaluate_brief_response(self.case, response).checks if c.name == "discrepancies_caught")
        self.assertEqual(check.score, 0)

    def test_invented_fact_is_detected(self):
        response = self.case["reference_answer"] + "\nThe estimated value is Rs.4 crore."
        guard = next(c for c in evaluate_brief_response(self.case, response).checks if c.name == "hallucination_guard")
        self.assertEqual(guard.score, 0)

    def test_prompt_contains_the_exact_template(self):
        prompt = get_system_prompt("tender-brief")
        for n, title in enumerate(("Basic Tender Information", "Important Dates & Timeline",
                "Eligibility & Qualification Criteria", "Detailed Scope of Work", "Commercial Terms",
                "Evaluation & Selection Process", "Documents Required", "Risk Analysis & Critical Points",
                "Final Bid Recommendation", "Open Points / Clarifications Required"), 1):
            self.assertIn(f"## {n}. {title}", prompt)
        for rule in ("Not stated in the tender", "[Clause x / Page n / Annexure]", "Never invent"):
            self.assertIn(rule, prompt)


if __name__ == "__main__":
    unittest.main()
