import unittest
from pathlib import Path

from app.agents.registry import AGENT_SYSTEM_PROMPTS
from scripts.evaluate_all_agents import EVALUATORS

BACKEND_DIR = Path(__file__).resolve().parents[1]


class AgentTrainingInventoryTests(unittest.TestCase):
    def test_every_registered_agent_has_an_evaluator(self):
        self.assertEqual(set(AGENT_SYSTEM_PROMPTS), set(EVALUATORS))

    def test_every_agent_has_training_artifacts(self):
        for agent_id, (module_name, _) in EVALUATORS.items():
            with self.subTest(agent=agent_id):
                training_dir = BACKEND_DIR / "training" / module_name
                self.assertTrue((training_dir / "dataset.jsonl").is_file())
                self.assertTrue((training_dir / "README.md").is_file())
                self.assertTrue((training_dir / "baseline.json").is_file())
                self.assertTrue((BACKEND_DIR / "app" / "evals" / f"{module_name}.py").is_file())
                self.assertTrue((BACKEND_DIR / "scripts" / f"evaluate_{module_name}.py").is_file())
