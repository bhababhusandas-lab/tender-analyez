import unittest
from pathlib import Path

from app.evals.bid_manager import load_cases
from app.evals.bid_pricing import evaluate_pricing_response
from app.agents.registry import get_system_prompt

DATASET = Path(__file__).resolve().parents[1] / "training" / "bid_pricing" / "dataset.jsonl"


class BidPricingEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = load_cases(DATASET)[0]

    def test_reference_answer_passes(self):
        self.assertEqual(evaluate_pricing_response(self.case, self.case["reference_answer"]).score, 100)

    def test_invented_l1_is_detected(self):
        response = self.case["reference_answer"] + "\nHistorical L1 was ₹65 lakh."
        result = evaluate_pricing_response(self.case, response)
        guard = next(c for c in result.checks if c.name == "market_hallucination_guard")
        self.assertEqual(guard.score, 0)

    def test_shallow_price_fails(self):
        self.assertFalse(evaluate_pricing_response(self.case, "Quote ₹69 lakh.").passed)

    def test_prompt_contains_grounded_pricing_contract(self):
        prompt = get_system_prompt("bid-pricing")
        for heading in ("## Cost basis", "## Market evidence", "## Price scenarios", "## Recommended quote", "## Sensitivity and approvals"):
            self.assertIn(heading, prompt)
        self.assertIn("No verified historical L1 data is available", prompt)
        self.assertIn("Never invent competitor identities", prompt)


if __name__ == "__main__":
    unittest.main()
