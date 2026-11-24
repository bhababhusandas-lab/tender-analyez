# Reviewed tenders

Real tenders whose analysis a person has checked. Each folder pins what the
deterministic part of the pipeline — evidence extraction
(`app/core/tender_evidence.py`) and condensing (`app/core/tender_condense.py`)
— must get right for that tender, and what it must never output.
`tests/test_reviewed_tenders.py` runs every folder; no model is called.

## Add a tender

1. Create `tests/reviewed_tenders/<short_name>/`.
2. Save the extracted text as `tender.txt` (keep it under ~500 KB):

   ```bash
   cd backend && .venv/bin/python -c "
   import sys
   from app.core.document_extract import extract_document_text
   print(extract_document_text(open(sys.argv[1], 'rb').read(), sys.argv[1]))
   " /path/to/tender.pdf > tests/reviewed_tenders/<short_name>/tender.txt
   ```

   For several files, put a `--- SOURCE DOCUMENT: <file name> ---` line before
   each one's text, as the upload API does.
3. Write `expected.json` from the reviewer's findings, not from what the
   extractor currently prints.
4. Run `.venv/bin/python -m pytest -q tests/test_reviewed_tenders.py`. A
   failure means the extractor needs fixing, not the expectation.

## expected.json

| Key | Meaning |
|---|---|
| `name`, `source`, `reviewed` | What the tender is and what the review found. Not checked. |
| `facts` | Field -> check. The field must be an agreed (non-conflicting) fact. |
| `absent_fields` | Fields that must have no candidate at all (for example no `Estimated Contract Value` when the tender states none). |
| `forbidden_amounts` | Field -> rupee amounts no candidate for that field may equal (a fee or EMD read as the contract value). |
| `forbidden_in_evidence_block` | Strings that must not appear in the evidence block given to the model. |
| `model_input` | Checks on the text the model receives: `contains` strings that must survive, with an optional `budget` (characters, default the pipeline's) and `"evidence": false` to check the condensed tender text alone. |

A fact check uses whichever keys fit the field:

- `"amount": 1000000` — the value in rupees (crore/lakh units are converted).
- `"date": "2026-10-03"`, `"time": "15:00"` — normalised date and 24-hour time.
- `"contains": ["..."]` — substrings of the value, case-insensitive.
- `"equals": "..."` — the exact value.
