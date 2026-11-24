import unittest
from pathlib import Path

from app.agents.registry import get_system_prompt
from app.evals.bid_manager import load_cases
from app.evals.doc_controller import evaluate_document_response

DATASET = Path(__file__).resolve().parents[1] / "training" / "doc_controller" / "dataset.jsonl"


class DocumentControllerEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = load_cases(DATASET)[0]

    def test_reference_answer_passes(self):
        self.assertEqual(evaluate_document_response(self.case, self.case["reference_answer"]).score, 100)

    def test_shallow_ready_claim_fails(self):
        self.assertFalse(evaluate_document_response(self.case, "The package is ready.").passed)

    def test_invented_acknowledgement_is_detected(self):
        response = self.case["reference_answer"] + "\nPortal acknowledgement number GEM/2026/12345 received."
        guard = next(c for c in evaluate_document_response(self.case, response).checks if c.name == "hallucination_guard")
        self.assertEqual(guard.score, 0)

    def test_prompt_contains_document_contract(self):
        prompt = get_system_prompt("doc-controller")
        for heading in ("## Source register", "## Document matrix", "## Version and validity", "## Package and deadline plan", "## Readiness verdict"):
            self.assertIn(heading, prompt)
        self.assertIn("Never invent vault records", prompt)


if __name__ == "__main__":
    unittest.main()
