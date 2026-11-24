import unittest
from pathlib import Path

from app.agents.registry import get_system_prompt
from app.evals.bid_manager import load_cases
from app.evals.it_support import evaluate_it_response

DATASET = Path(__file__).resolve().parents[1] / "training" / "it_support" / "dataset.jsonl"


class ITSupportEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = load_cases(DATASET)[0]

    def test_reference_answer_passes(self):
        self.assertEqual(evaluate_it_response(self.case, self.case["reference_answer"]).score, 100)

    def test_shallow_retry_fails(self):
        self.assertFalse(evaluate_it_response(self.case, "Refresh and try again later.").passed)

    def test_unsafe_secret_request_is_detected(self):
        response = self.case["reference_answer"] + "\nSend me your DSC PIN."
        guard = next(c for c in evaluate_it_response(self.case, response).checks if c.name == "unsafe_claim_guard")
        self.assertEqual(guard.score, 0)

    def test_prompt_contains_incident_contract(self):
        prompt = get_system_prompt("it-support")
        for heading in ("## Incident summary", "## Evidence-based diagnosis", "## Recovery runbook", "## Escalation and proof", "## Prevention"):
            self.assertIn(heading, prompt)
        self.assertIn("Never request or expose passwords", prompt)


if __name__ == "__main__":
    unittest.main()
