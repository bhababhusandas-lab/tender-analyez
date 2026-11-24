import unittest
from pathlib import Path

from app.evals.bid_manager import load_cases
from app.evals.legal_compliance import evaluate_legal_response
from app.agents.registry import get_system_prompt

DATASET = Path(__file__).resolve().parents[1] / "training" / "legal_compliance" / "dataset.jsonl"


class LegalComplianceEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = load_cases(DATASET)[0]

    def test_reference_answer_passes(self):
        result = evaluate_legal_response(self.case, self.case["reference_answer"])
        self.assertTrue(result.passed)
        self.assertEqual(result.score, 100)

    def test_shallow_approval_fails(self):
        self.assertFalse(evaluate_legal_response(self.case, "The terms look standard and acceptable.").passed)

    def test_invented_liability_cap_is_detected(self):
        response = self.case["reference_answer"] + "\nAggregate liability is already capped under the tender."
        result = evaluate_legal_response(self.case, response)
        guard = next(check for check in result.checks if check.name == "hallucination_guard")
        self.assertEqual(guard.score, 0)

    def test_prompt_contains_legal_response_contract(self):
        prompt = get_system_prompt("legal-compliance")
        for heading in ("## Risk rating", "## Clause review", "## Missing clauses", "## Pre-bid queries", "## Action plan"):
            self.assertIn(heading, prompt)
        self.assertIn("only for a material ambiguity or risk actually found", prompt)
        self.assertIn("Do not create filler questions", prompt)
        self.assertIn("end with a literal question mark", prompt)

    def test_typographic_hyphen_in_prebid_heading_is_supported(self):
        response = self.case["reference_answer"].replace("Pre-bid queries", "Pre‑bid queries")
        result = evaluate_legal_response(self.case, response)
        queries = next(check for check in result.checks if check.name == "prebid_queries")
        self.assertEqual(queries.score, 1)


if __name__ == "__main__":
    unittest.main()
