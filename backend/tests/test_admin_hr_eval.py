import unittest
from pathlib import Path

from app.agents.registry import get_system_prompt
from app.evals.admin_hr import evaluate_hr_response
from app.evals.bid_manager import load_cases

DATASET = Path(__file__).resolve().parents[1] / "training" / "admin_hr" / "dataset.jsonl"


class AdminHREvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = load_cases(DATASET)[0]

    def test_reference_answer_passes(self):
        self.assertEqual(evaluate_hr_response(self.case, self.case["reference_answer"]).score, 100)

    def test_shallow_ready_claim_fails(self):
        self.assertFalse(evaluate_hr_response(self.case, "The team is compliant and ready.").passed)

    def test_invented_threshold_is_detected(self):
        response = self.case["reference_answer"] + "\nThe statutory ESI threshold is ₹25,000."
        guard = next(c for c in evaluate_hr_response(self.case, response).checks if c.name == "hallucination_guard")
        self.assertEqual(guard.score, 0)

    def test_prompt_contains_hr_contract(self):
        prompt = get_system_prompt("admin-hr")
        for heading in ("## Evidence boundary", "## Manpower matrix", "## Statutory records", "## Deployment and gap plan", "## Readiness verdict"):
            self.assertIn(heading, prompt)
        self.assertIn("Never invent PF or ESI thresholds", prompt)


if __name__ == "__main__":
    unittest.main()
