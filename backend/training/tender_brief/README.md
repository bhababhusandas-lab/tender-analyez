# Tender Brief evaluation

This locked synthetic case measures whether the agent fills the nine-section Tender Brief template strictly from the tender documents: every heading in order, exact dates and amounts, clause/annexure citations, "Not stated in the tender" for gaps, and — most importantly — both values of every contradiction between the main body and an annexure in section 9.

Run the reference self-check:

```bash
.venv/bin/python scripts/evaluate_tender_brief.py
```

Run the configured live model:

```bash
.venv/bin/python scripts/evaluate_tender_brief.py --live
```

The shared dataset loader requires an `expected.decision`; the brief makes no bid decision, so the scorer ignores that field. The dataset is synthetic and must not be treated as an actual tender.
