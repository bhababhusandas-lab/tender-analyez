import unittest
from pathlib import Path

from app.evals.bid_manager import load_cases
from app.evals.technical_expert import evaluate_technical_response
from app.agents.registry import get_system_prompt


DATASET = Path(__file__).resolve().parents[1] / "training" / "technical_expert" / "dataset.jsonl"


class TechnicalExpertEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = load_cases(DATASET)[0]

    def test_reference_answer_passes(self):
        result = evaluate_technical_response(self.case, self.case["reference_answer"])
        self.assertTrue(result.passed)
        self.assertEqual(result.score, 100)

    def test_shallow_compliance_claim_fails(self):
        result = evaluate_technical_response(self.case, "All specifications are compliant.")
        self.assertFalse(result.passed)

    def test_unsupported_certificate_claim_is_detected(self):
        response = self.case["reference_answer"] + "\nThe bidder is ISO 27001 certified."
        result = evaluate_technical_response(self.case, response)
        guard = next(check for check in result.checks if check.name == "hallucination_guard")
        self.assertEqual(guard.score, 0)

    def test_negated_site_survey_claim_is_allowed(self):
        response = self.case["reference_answer"] + "\nNo site survey completed."
        result = evaluate_technical_response(self.case, response)
        guard = next(check for check in result.checks if check.name == "hallucination_guard")
        self.assertEqual(guard.score, 1)

    def test_prompt_contains_technical_response_contract(self):
        prompt = get_system_prompt("technical-expert")
        for heading in ("## Requirements", "## Compliance matrix", "## Methodology", "## Evidence gaps", "## Action plan"):
            self.assertIn(heading, prompt)
        self.assertIn("Do not invent a stage merely to reach a paragraph count", prompt)


if __name__ == "__main__":
    unittest.main()
