import unittest
from pathlib import Path

from app.agents.registry import get_system_prompt
from app.evals.bid_manager import load_cases
from app.evals.technical_writer import evaluate_writer_response

DATASET = Path(__file__).resolve().parents[1] / "training" / "technical_writer" / "dataset.jsonl"


class TechnicalWriterEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = load_cases(DATASET)[0]

    def test_reference_answer_passes(self):
        self.assertEqual(evaluate_writer_response(self.case, self.case["reference_answer"]).score, 100)

    def test_shallow_layout_advice_fails(self):
        self.assertFalse(evaluate_writer_response(self.case, "Use a clean professional layout.").passed)

    def test_invented_certification_is_detected(self):
        response = self.case["reference_answer"] + "\nThe bidder is ISO 27001 certified."
        guard = next(c for c in evaluate_writer_response(self.case, response).checks if c.name == "hallucination_guard")
        self.assertEqual(guard.score, 0)

    def test_prompt_contains_writer_contract(self):
        prompt = get_system_prompt("technical-writer")
        for heading in ("## Content inventory", "## Proposal structure", "## Executive summary", "## Compliance mapping", "## Visual and production notes"):
            self.assertIn(heading, prompt)
        self.assertIn("Never invent certifications", prompt)


if __name__ == "__main__":
    unittest.main()
