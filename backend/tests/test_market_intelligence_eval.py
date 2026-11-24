import unittest
from pathlib import Path

from app.agents.registry import get_system_prompt
from app.evals.bid_manager import load_cases
from app.evals.market_intelligence import evaluate_market_response

DATASET = Path(__file__).resolve().parents[1] / "training" / "market_intelligence" / "dataset.jsonl"


class MarketIntelligenceEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = load_cases(DATASET)[0]

    def test_reference_answer_passes(self):
        self.assertEqual(evaluate_market_response(self.case, self.case["reference_answer"]).score, 100)

    def test_shallow_market_claim_fails(self):
        self.assertFalse(evaluate_market_response(self.case, "The market is growing quickly.").passed)

    def test_invented_competitor_is_detected(self):
        response = self.case["reference_answer"] + "\n" + ("Evidence reviewed. " * 10) + "Apex Digital won five tenders."
        guard = next(c for c in evaluate_market_response(self.case, response).checks if c.name == "hallucination_guard")
        self.assertEqual(guard.score, 0)

    def test_prompt_contains_market_contract(self):
        prompt = get_system_prompt("market-intelligence")
        for heading in ("## Source register", "## Observed market", "## Competitor evidence", "## Opportunity outlook", "## Uncertainty and actions"):
            self.assertIn(heading, prompt)
        self.assertIn("Never invent competitors", prompt)


if __name__ == "__main__":
    unittest.main()
