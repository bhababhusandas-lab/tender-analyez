import unittest
from pathlib import Path

from app.agents.registry import get_system_prompt
from app.evals.bid_manager import load_cases
from app.evals.govt_relations import evaluate_relations_response

DATASET = Path(__file__).resolve().parents[1] / "training" / "govt_relations" / "dataset.jsonl"


class GovernmentRelationsEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = load_cases(DATASET)[0]

    def test_reference_answer_passes(self):
        self.assertEqual(evaluate_relations_response(self.case, self.case["reference_answer"]).score, 100)

    def test_vague_networking_plan_fails(self):
        self.assertFalse(evaluate_relations_response(self.case, "Meet stakeholders and build relationships.").passed)

    def test_improper_influence_is_detected(self):
        response = self.case["reference_answer"] + "\nWe can influence the evaluation committee."
        guard = next(c for c in evaluate_relations_response(self.case, response).checks if c.name == "integrity_guard")
        self.assertEqual(guard.score, 0)

    def test_prompt_contains_relations_contract(self):
        prompt = get_system_prompt("govt-relations")
        for heading in ("## Engagement objective", "## Permitted channels", "## Stakeholder register", "## Communication draft", "## Integrity controls and log"):
            self.assertIn(heading, prompt)
        self.assertIn("Never propose gifts", prompt)


if __name__ == "__main__":
    unittest.main()
