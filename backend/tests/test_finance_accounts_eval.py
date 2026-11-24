import unittest
from pathlib import Path

from app.evals.bid_manager import load_cases
from app.evals.finance_accounts import evaluate_finance_response
from app.agents.registry import get_system_prompt

DATASET = Path(__file__).resolve().parents[1] / "training" / "finance_accounts" / "dataset.jsonl"


class FinanceAccountsEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = load_cases(DATASET)[0]

    def test_reference_answer_passes(self):
        result = evaluate_finance_response(self.case, self.case["reference_answer"])
        self.assertEqual(result.score, 100)

    def test_wrong_quote_is_detected(self):
        response = self.case["reference_answer"] + "\nFinal quote is ₹69,04,300."
        result = evaluate_finance_response(self.case, response)
        guard = next(c for c in result.checks if c.name == "hallucination_guard")
        self.assertEqual(guard.score, 0)

    def test_shallow_price_fails(self):
        self.assertFalse(evaluate_finance_response(self.case, "Quote competitively.").passed)

    def test_prompt_contains_finance_response_contract(self):
        prompt = get_system_prompt("finance-accounts")
        for heading in ("## Assumptions", "## Financial compliance", "## BOQ", "## Pricing summary", "## Risks and approvals"):
            self.assertIn(heading, prompt)
        self.assertIn("verified customer costs", prompt)
        self.assertIn("generic statutory-document requirements", prompt)

    def test_generic_tender_defaults_are_rejected(self):
        response = self.case["reference_answer"] + "\nPer standard government tender practice, three ITRs are mandatory."
        result = evaluate_finance_response(self.case, response)
        guard = next(c for c in result.checks if c.name == "hallucination_guard")
        self.assertEqual(guard.score, 0)

    def test_trailing_not_specified_negates_forbidden_term(self):
        response = self.case["reference_answer"] + "\nDefect-liability period and insurance terms are Not specified in tender."
        result = evaluate_finance_response(self.case, response)
        guard = next(c for c in result.checks if c.name == "hallucination_guard")
        self.assertEqual(guard.score, 1)


if __name__ == "__main__":
    unittest.main()
