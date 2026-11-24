# QA Reviewer evaluation

This locked synthetic case measures whether the agent performs an evidence-grounded final bid audit, catches every supplied blocking defect, and gives an explicit submission verdict.

Run the reference self-check:

```bash
.venv/bin/python scripts/evaluate_qa_reviewer.py
```

Run the configured live model:

```bash
.venv/bin/python scripts/evaluate_qa_reviewer.py --live
```

The dataset is synthetic and must not be treated as an actual tender. A human authorised reviewer remains responsible for final submission approval.
