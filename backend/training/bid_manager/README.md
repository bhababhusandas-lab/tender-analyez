# Bid Manager training and evaluation

This directory is the first measurable training asset for the Bid Manager. It
does **not** fine-tune a model yet. It establishes the reviewed examples and
regression tests needed to know whether a later prompt, retrieval, or
fine-tuning change is actually an improvement.

## Dataset contract

Each line in `dataset.jsonl` is one self-contained case validated by
`case.schema.json`. Keep personally identifiable information and customer
secrets out of the dataset. Real examples must be anonymised, source-labelled,
and approved by a procurement reviewer before moving into `validation` or
`test`.

Never train on validation or test cases. Recommended growth target:

- 60% training cases
- 20% validation cases
- 20% locked test cases
- Balanced BID, NO-BID, and CONDITIONAL decisions
- Coverage across GeM, CPPP, IREPS, state portals, goods, services, and works

## Run the deterministic baseline

From `backend/`:

```bash
.venv/bin/python scripts/evaluate_bid_manager.py
```

With saved candidate responses:

```bash
.venv/bin/python scripts/evaluate_bid_manager.py --responses path/to/responses.jsonl
```

Select specific cases with repeatable `--case` flags when iterating on a known
failure without spending quota on the rest of the locked set.

The response file contains one JSON object per line:

```json
{"id": "bm_gem_it_bid", "response": "...candidate answer..."}
```

To call the configured live model (this consumes provider quota):

```bash
.venv/bin/python scripts/evaluate_bid_manager.py --live --split test \
  --output training/bid_manager/reports/latest.json \
  --response-output training/bid_manager/reports/latest-responses.jsonl
```

Response files can contain sensitive tender content. Save them only for
synthetic or explicitly approved, anonymised cases; the flag is optional so a
normal run does not persist model output.

The deterministic score checks the decision, required sections, grounded
requirements, exact numeric facts, forbidden claims, and explicit uncertainty
labelling. Cases pass at 80 by default. Expert review remains mandatory for
legal correctness, usefulness, and subtle hallucinations.

## Promotion gate

A Bid Manager change is ready for production only when:

1. The locked test-set average does not regress.
2. Every hard-disqualifier case reaches the correct decision.
3. No forbidden or unsupported claim appears.
4. A procurement expert approves a blind sample of outputs.
5. Latency and provider cost remain inside the product budget.
