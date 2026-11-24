import unittest
from pathlib import Path

from app.agents.registry import get_system_prompt
from app.evals.bid_manager import load_cases
from app.evals.qa_reviewer import evaluate_qa_response

DATASET = Path(__file__).resolve().parents[1] / "training" / "qa_reviewer" / "dataset.jsonl"


class QAReviewerEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = load_cases(DATASET)[0]

    def test_reference_answer_passes(self):
        self.assertEqual(evaluate_qa_response(self.case, self.case["reference_answer"]).score, 100)

    def test_shallow_go_fails(self):
        self.assertFalse(evaluate_qa_response(self.case, "Everything looks fine. GO.").passed)

    def test_invented_requirement_is_detected(self):
        response = self.case["reference_answer"] + "\nThree years of audited statements are mandatory."
        guard = next(c for c in evaluate_qa_response(self.case, response).checks if c.name == "hallucination_guard")
        self.assertEqual(guard.score, 0)

    def test_prompt_contains_qa_response_contract(self):
        prompt = get_system_prompt("qa-reviewer")
        for heading in ("## Review scope", "## Compliance checklist", "## Blocking defects", "## Corrections and re-check", "## Submission verdict"):
            self.assertIn(heading, prompt)
        self.assertIn("Use only the supplied tender requirements", prompt)


if __name__ == "__main__":
    unittest.main()
