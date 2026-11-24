import unittest
from pathlib import Path

from app.evals.bid_manager import evaluate_many, evaluate_response, load_cases
from app.agents.registry import get_system_prompt


DATASET = Path(__file__).resolve().parents[1] / "training" / "bid_manager" / "dataset.jsonl"


class BidManagerEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_cases(DATASET)

    def test_seed_dataset_has_all_splits_and_decisions(self):
        self.assertEqual({case["split"] for case in self.cases}, {"train", "validation", "test"})
        self.assertEqual(
            {case["expected"]["decision"] for case in self.cases},
            {"BID", "NO-BID", "CONDITIONAL"},
        )

    def test_locked_test_split_covers_all_decisions(self):
        test_decisions = {
            case["expected"]["decision"] for case in self.cases if case["split"] == "test"
        }
        self.assertEqual(test_decisions, {"BID", "NO-BID", "CONDITIONAL"})

    def test_reference_answers_pass(self):
        responses = {case["id"]: case["reference_answer"] for case in self.cases}
        results = evaluate_many(self.cases, responses)
        self.assertTrue(all(result.passed for result in results))

    def test_unsupported_shallow_answer_fails(self):
        result = evaluate_response(self.cases[0], "Decision: BID. Looks suitable.")
        self.assertFalse(result.passed)
        self.assertLess(result.score, 50)

    def test_forbidden_claim_is_detected(self):
        case = self.cases[2]
        response = case["reference_answer"] + "\nNo EMD is required."
        result = evaluate_response(case, response)
        guard = next(check for check in result.checks if check.name == "hallucination_guard")
        self.assertEqual(guard.score, 0)

    def test_later_conditional_phrase_does_not_rescue_wrong_opening_verdict(self):
        case = self.cases[2]
        response = case["reference_answer"].replace("CONDITIONAL BID", "BID", 1)
        result = evaluate_response(case, response)
        decision = next(check for check in result.checks if check.name == "decision")
        self.assertEqual(decision.score, 0)

    def test_unicode_hyphens_match_grounded_requirements(self):
        case = self.cases[2]
        response = case["reference_answer"].replace("key-personnel", "key‑personnel")
        result = evaluate_response(case, response)
        grounded = next(check for check in result.checks if check.name == "grounded_requirements")
        self.assertEqual(grounded.score, 1)

    def test_number_words_and_digits_are_equivalent(self):
        case = self.cases[2]
        response = case["reference_answer"]
        response = response.replace("seven years", "7 years")
        response = response.replace("five years", "5 years")
        response = response.replace("four municipal assignments", "4 municipal assignments")
        response = response.replace("three municipal assignments", "3 municipal assignments")
        result = evaluate_response(case, response)
        numeric = next(check for check in result.checks if check.name == "numeric_facts")
        self.assertEqual(numeric.score, 1)

    def test_common_indian_financial_and_duration_formats_are_equivalent(self):
        case = next(case for case in self.cases if case["id"] == "bm_cppp_facility_bid")
        response = case["reference_answer"].replace("₹1.5 crore", "₹1.5 cr").replace("24 months", "24-month")
        result = evaluate_response(case, response)
        numeric = next(check for check in result.checks if check.name == "numeric_facts")
        self.assertEqual(numeric.score, 1)

    def test_non_breaking_space_cannot_hide_bad_percentage(self):
        case = next(case for case in self.cases if case["id"] == "bm_cppp_facility_bid")
        response = case["reference_answer"] + "\nThe EMD is 0.2\u202f% of value."
        result = evaluate_response(case, response)
        guard = next(check for check in result.checks if check.name == "hallucination_guard")
        self.assertEqual(guard.score, 0)

    def test_bid_manager_prompt_contains_evaluation_contract(self):
        prompt = get_system_prompt("bid-manager")
        for heading in ("## Decision", "## Eligibility", "## Deadlines", "## Risks", "## Action plan"):
            self.assertIn(heading, prompt)
        self.assertIn('Write "Not specified in tender"', prompt)
        self.assertIn("Repeat every material figure exactly as supplied", prompt)
        self.assertIn("verify the arithmetic", prompt)
        self.assertIn("Apply this verdict hierarchy in order", prompt)
        self.assertIn("A pending or under-review registration/approval is unmet", prompt)


if __name__ == "__main__":
    unittest.main()
