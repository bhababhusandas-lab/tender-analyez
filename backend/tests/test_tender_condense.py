"""Smart selection of oversized tender text (the real RR-2 tender is ~427k characters)."""
import re
from pathlib import Path

import pytest

from app.core.tender_condense import TENDER_CHAR_BUDGET, build_model_input, condense_tender_text
from app.core.tender_evidence import extract_tender_evidence, format_evidence_block

FIXTURE = Path(__file__).parent / "reviewed_tenders" / "rr2_radial_road_pkg1" / "tender.txt"


@pytest.fixture(scope="module")
def raw():
    return FIXTURE.read_text()


@pytest.fixture(scope="module")
def condensed(raw):
    return condense_tender_text(raw)


def test_fixture_is_over_budget(raw):
    assert len(raw) > 4 * TENDER_CHAR_BUDGET


def test_output_is_within_budget(condensed):
    assert len(condensed) <= TENDER_CHAR_BUDGET


@pytest.mark.parametrize("needle", [
    "12,37,20,000",            # EMD
    "30.09.2026 @ 3.00 PM",    # bid submission
    "30.09.2026 @ 3.30 PM",    # technical bid opening
    "2AN",                     # bid-capacity formula
    "412.38",                  # similar work
    "206.20",                  # liquid assets
])
def test_key_facts_survive(condensed, needle):
    assert needle in condensed


def test_states_how_much_was_omitted(condensed):
    first = condensed.split("\n", 1)[0]
    assert first.startswith("[Condensed input:")
    assert re.search(r"omitted \d+ passages", first)


def test_source_headers_are_kept_for_citations(condensed):
    assert "--- SOURCE DOCUMENT: RR2 Pkg 1 Bid document.pdf ---" in condensed
    assert "--- PAGE 4 ---" in condensed
    # The NIT page is still cited correctly by the evidence extractor.
    evidence = extract_tender_evidence(condensed)
    emd = next(item for item in evidence if item.field == "EMD Amount")
    assert (emd.source, emd.page) == ("RR2 Pkg 1 Bid document.pdf", "4")


def test_original_order_is_preserved(raw, condensed):
    def sequence(text):
        doc, out = -1, []
        for line in text.split("\n"):
            if line.startswith("--- SOURCE DOCUMENT:"):
                doc += 1
            match = re.match(r"--- PAGE (\d+) ---", line)
            if match:
                out.append((doc, int(match.group(1))))
        return out

    kept = sequence(condensed)
    assert len(kept) > 20
    assert kept == sorted(kept)
    assert set(kept) <= set(sequence(raw))


def test_boq_rows_are_low_priority_but_totals_kept(raw, condensed):
    assert "Total(INR): 12371634251" in condensed
    header = "Subwork Name Specification Number Quantity UOM"
    assert condensed.count(header) <= raw.count(header) * 0.05


def test_short_input_is_unchanged():
    text = "--- SOURCE DOCUMENT: a.pdf ---\nEMD Amount: Rs 5,000\n"
    assert condense_tender_text(text) == text


def test_evidence_block_comes_first_and_total_fits(raw):
    block = format_evidence_block(extract_tender_evidence(raw))
    text = build_model_input(raw, block)
    assert text.startswith("=== DETERMINISTIC METADATA EVIDENCE ===")
    assert len(text) <= TENDER_CHAR_BUDGET


def test_reanalysis_update_sections_stay_first_and_whole(raw):
    update = "=== UPDATE 1 (added 30 Sep 2026): corrigendum.pdf — overrides earlier documents where they conflict ===\n" \
             "--- SOURCE DOCUMENT: corrigendum.pdf ---\nBid Submission Deadline: 07.10.2026 15:00\nPre-bid replies attached."
    note = "=== UPDATE FROM THE USER (not from the tender) ===\n" \
           "--- SOURCE DOCUMENT: Update note from the user ---\nWe now have a JV partner."
    text = f"{update}\n\n{note}\n\n=== ORIGINAL TENDER DOCUMENTS ===\n{raw}"
    out = condense_tender_text(text)
    assert len(out) <= TENDER_CHAR_BUDGET
    body = out.split("\n", 1)[1]
    assert body.startswith("=== UPDATE 1")
    assert "07.10.2026 15:00" in body and "We now have a JV partner." in body
    assert body.index("=== UPDATE FROM THE USER") < body.index("=== ORIGINAL TENDER DOCUMENTS ===")
    assert "12,37,20,000" in body


def test_final_briefing_input_fits_and_keeps_evidence():
    from pathlib import Path
    from app.core.tender_condense import condense_for_final, FINAL_TENDER_BUDGET, FINAL_TEAM_BUDGET
    raw = (Path(__file__).parent / "reviewed_tenders" / "rr2_radial_road_pkg1" / "tender.txt").read_text()
    evidence = "=== DETERMINISTIC METADATA EVIDENCE ===\n- EMD Amount: Rs 12,37,20,000\n=== END DETERMINISTIC METADATA EVIDENCE ==="
    reports = [(f"AGENT {i}", "line of analysis\n" * 2000) for i in range(11)]
    tender, team = condense_for_final(evidence + "\n\n" + raw, reports)
    assert tender.startswith("=== DETERMINISTIC METADATA EVIDENCE ===") and "12,37,20,000" in tender
    assert len(tender) <= FINAL_TENDER_BUDGET + 2_000
    assert len(team) <= FINAL_TEAM_BUDGET + 11 * 200
    assert team.count("[… report shortened for the final briefing]") == 11
