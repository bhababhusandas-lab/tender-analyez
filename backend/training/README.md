# Specialist agent evaluation suite

All 12 registered Unique Type specialists have a synthetic locked dataset, deterministic evaluator, baseline record, tests, and a standalone evaluation command.

Run the full deterministic fleet check:

```bash
.venv/bin/python scripts/evaluate_all_agents.py
```

Run repository tests:

```bash
.venv/bin/python -m unittest discover -s tests -q
```

These evaluations test response contracts and evidence discipline; they are not model fine-tuning and do not replace authorised tender, legal, finance, HR, security, or submission review. Live-model baseline files distinguish measured scores from runs deferred because provider quota was unavailable.
