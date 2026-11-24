import json
import re
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.core.db.session import get_db
from app.core.db.models import Bid, User
from app.core.security.auth import get_current_user

router = APIRouter()

AGENT_NAMES = {
    "bid-manager": "Bid Manager AI",
    "legal-compliance": "Legal / Compliance AI",
    "technical-expert": "Technical Expert AI",
    "finance-accounts": "Finance & Accounts AI",
    "doc-controller": "Document Controller AI",
    "admin-hr": "Admin / HR AI",
}

AGENT_ORDER = list(AGENT_NAMES.keys())
REPORT_TIMEZONE = ZoneInfo("Asia/Kolkata")


def report_generated_timestamp(moment: datetime | None = None) -> str:
    """Return an explicit India-local timestamp for customer-facing reports."""
    current = moment or datetime.now(REPORT_TIMEZONE)
    if current.tzinfo is None:
        current = current.replace(tzinfo=REPORT_TIMEZONE)
    return current.astimezone(REPORT_TIMEZONE).strftime("%d %b %Y, %I:%M %p IST")


def strip_markdown(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    # Remove Markdown heading markers without erasing a literal "#" table
    # column used for row numbering.
    text = re.sub(r'^#{1,4}\s+', '', text)
    # replace characters unsupported by built-in PDF fonts
    text = text.replace('\ufe0f', '')  # emoji variation selector left after ⚠️/✅ swaps
    text = text.replace('₹', 'Rs.').replace('’', "'").replace('‘', "'")
    text = text.replace('“', '"').replace('”', '"').replace('–', '-').replace('—', '--')
    text = text.replace('⚠️', 'Needs review').replace('⚠', 'Needs review')
    text = text.replace('✅', 'Verified').replace('❌', 'Not verified')
    text = text.replace('❤', '<3').replace('▶', '>').replace('•', '-')
    text = text.replace('≥', '>=').replace('≤', '<=').replace('→', '->').replace('×', 'x').replace('✓', 'Yes')
    # strip any remaining non-latin-1 characters
    text = text.encode('latin-1', errors='replace').decode('latin-1')
    return text


def _table_cells(line: str) -> list[str]:
    return [strip_markdown(cell.strip()) for cell in line.strip().strip("|").split("|")]


def _is_table_divider(line: str) -> bool:
    cells = _table_cells(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def render_markdown(pdf, content: str) -> None:
    """Render the supported Markdown subset as real PDF structure.

    Agent reports intentionally use headings, lists and tables. Flattening that
    syntax made exports look like raw model output, so the PDF renderer now
    interprets it instead of printing pipes, hashes and horizontal rules.
    """
    lines = content.replace("\r\n", "\n").split("\n")
    index = 0
    while index < len(lines):
        raw = lines[index].strip()
        if not raw:
            pdf.ln(1.5)
            index += 1
            continue
        if re.fullmatch(r"(?:-{3,}|_{3,}|\*{3,})", raw):
            index += 1
            continue

        heading = re.match(r"^(#{1,4})\s+(.+)$", raw)
        bold_heading = re.fullmatch(r"\*\*([^*]+)\*\*", raw)
        if heading or bold_heading:
            label = heading.group(2) if heading else bold_heading.group(1)
            pdf.ln(2)
            level = len(heading.group(1)) if heading else 0
            if level >= 3:
                # Sub-headings ("### 3.1 ...") read as a small coloured label.
                pdf.ln(0.5)
                pdf.set_font("Helvetica", "B", 8.5)
                pdf.set_text_color(51, 85, 130)
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 5, strip_markdown(label))
            else:
                pdf.set_font("Helvetica", "B", 10 if not heading or level > 1 else 12)
                pdf.set_text_color(24, 38, 58)
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 6, strip_markdown(label))
            pdf.set_text_color(40, 40, 40)
            index += 1
            continue

        if raw.startswith("|") and index + 1 < len(lines) and _is_table_divider(lines[index + 1]):
            from fpdf.fonts import FontFace

            headers = _table_cells(raw)
            rows: list[list[str]] = []
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                if not _is_table_divider(lines[index]):
                    row = _table_cells(lines[index])
                    rows.append((row + [""] * len(headers))[:len(headers)])
                index += 1
            # fpdf2 handles wrapping and page breaks inside table cells.
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(30, 41, 59)
            pdf.set_fill_color(255, 255, 255)
            pdf.set_draw_color(203, 213, 225)
            with pdf.table(
                width=190,
                # Row-number columns ("#") need a fraction of a text column.
                col_widths=tuple(0.25 if h.strip() in ("#", "No.", "S.No") else 1 for h in headers),
                line_height=5,
                text_align="LEFT",
                headings_style=FontFace(
                    emphasis="BOLD",
                    color=(255, 255, 255),
                    fill_color=(30, 41, 59),
                ),
                first_row_as_headings=True,
                cell_fill_color=(248, 250, 252),
                cell_fill_mode="EVEN_ROWS",
                borders_layout="HORIZONTAL_LINES",
            ) as table:
                table.row(headers)
                for row in rows:
                    table.row(row)
            pdf.ln(2)
            pdf.set_x(pdf.l_margin)
            continue

        if re.match(r"^[-*]\s+", raw):
            pdf.set_font("Helvetica", "", 8)
            pdf.set_x(13)
            pdf.multi_cell(184, 5, "- " + strip_markdown(re.sub(r"^[-*]\s+", "", raw)))
            index += 1
            continue

        numbered = re.match(r"^(\d+)\.\s+(.+)$", raw)
        if numbered:
            pdf.set_font("Helvetica", "", 8)
            pdf.set_x(13)
            pdf.multi_cell(184, 5, f"{numbered.group(1)}. {strip_markdown(numbered.group(2))}")
            index += 1
            continue

        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(40, 40, 40)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 5, strip_markdown(raw))
        index += 1


# ── Summary extraction ─────────────────────────────────────────────────────
# The default export is a one-to-two page brief. Each point is taken once from
# the agent that owns it, instead of printing every agent's full report (which
# repeated the same eligibility gaps many times over ~12 pages).
SUMMARY_RISKS = 3
SUMMARY_ACTIONS = 5
_MET_STATUS = re.compile(r"\b(meets?|met|compliant|verified|yes|available)\b", re.I)
_UNMET_STATUS = re.compile(r"\b(not|don'?t|partial|missing|needs?|gap|unverified|no)\b", re.I)


def _heading_text(line: str) -> str | None:
    raw = line.strip()
    heading = re.match(r"^#{1,4}\s+(.+)$", raw)
    if heading:
        return heading.group(1).replace("**", "").strip()
    bold = re.fullmatch(r"\*\*([^*]+)\*\*", raw)
    return bold.group(1).strip() if bold else None


def split_sections(markdown: str) -> list[tuple[str, str]]:
    """Split an agent report into (heading, body) pairs.

    Reports that use # headings also use whole-line bold for values such as
    "**NOT CALCULABLE**", so bold lines only count as headings when a report
    has no # headings at all.
    """
    lines = (markdown or "").replace("\r\n", "\n").split("\n")
    hash_headings = any(re.match(r"^\s*#{1,4}\s+", line) for line in lines)
    sections: list[tuple[str, list[str]]] = [("", [])]
    for line in lines:
        title = _heading_text(line)
        if title is not None and hash_headings and not re.match(r"^\s*#", line):
            title = None
        if title is not None:
            sections.append((title, []))
        else:
            sections[-1][1].append(line)
    return [(title, "\n".join(body).strip()) for title, body in sections]


def find_section(markdown: str, pattern: str) -> tuple[str, str] | None:
    for title, body in split_sections(markdown):
        if title and re.search(pattern, title, re.I):
            return title, body
    return None


def _table(body: str) -> tuple[list[str], list[list[str]]] | None:
    lines = [line for line in body.split("\n") if line.strip()]
    for i, line in enumerate(lines[:-1]):
        if line.strip().startswith("|") and _is_table_divider(lines[i + 1]):
            headers = [cell.strip() for cell in line.strip().strip("|").split("|")]
            rows = []
            for row_line in lines[i + 2:]:
                if not row_line.strip().startswith("|"):
                    break
                if not _is_table_divider(row_line):
                    cells = [cell.strip() for cell in row_line.strip().strip("|").split("|")]
                    rows.append((cells + [""] * len(headers))[:len(headers)])
            return headers, rows
    return None


def _as_table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(cell.replace("|", "/") for cell in row) + " |" for row in rows]
    return "\n".join(out)


def _first_items(body: str, limit: int) -> str:
    """Keep a section's first `limit` table rows or list items."""
    table = _table(body)
    if table:
        headers, rows = table
        return _as_table(headers, rows[:limit])
    items = [line.strip() for line in body.split("\n") if re.match(r"^\s*(?:[-*]|\d+\.)\s+", line)]
    if items:
        return "\n".join(items[:limit])
    return body


def _eligibility_gaps(body: str) -> str:
    table = _table(body)
    if not table:
        return _first_items(body, 8)
    headers, rows = table
    lowered = [h.lower() for h in headers]
    criterion = next((i for i, h in enumerate(lowered) if "criter" in h or "requirement" in h), 1 if len(headers) > 1 else 0)
    status = next((i for i, h in enumerate(lowered) if "status" in h), None)
    notes = next((i for i, h in enumerate(lowered) if "evidence" in h or "note" in h or "gap" in h), None)
    gaps = []
    for row in rows:
        verdict = " ".join(row[i] for i in range(len(row)) if i != criterion) if status is None else row[status]
        if _UNMET_STATUS.search(verdict) or not _MET_STATUS.search(verdict):
            label = row[status] if status is not None else verdict
            gap = [row[criterion], re.sub(r"^[^\w(]+", "", label).strip()]
            if notes is not None:
                # "[FROM YOUR PROFILE] PAN not in profile" -> "PAN not in profile"
                gap.append(re.sub(r"\[FROM [^\]]*\]\s*", "", row[notes]).strip() or "-")
            gaps.append(gap)
    if not gaps:
        return "No eligibility gaps were identified."
    return _as_table(["Criterion", "Status", "What's missing"] if notes is not None else ["Criterion", "Status"], gaps)


def _overview(final: str) -> str:
    """The tender itself in two or three sentences, from the MD's executive summary."""
    found = find_section(final, r"EXECUTIVE SUMMARY|OVERVIEW")
    if not found:
        return ""
    text = " ".join(line.strip() for line in found[1].split("\n")
                    if line.strip() and not re.fullmatch(r"(?:-{3,}|_{3,}|\*{3,})", line.strip()))
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    # Stop before the MD turns to our own readiness; that is what the rest of the brief covers.
    keep = []
    for sentence in sentences[:3]:
        if keep and re.search(r"\b(our|we|lacks?|missing|gaps?|eligib\w*|profile|bid is|recommend\w*|conditional)\b", sentence, re.I):
            break
        keep.append(sentence)
    return " ".join(keep)


def summary_sections(pipeline: dict) -> list[tuple[str, str]]:
    """Return the six brief sections, each taken once from its owning agent."""
    final = str(pipeline.get("final", ""))
    manager = str(pipeline.get("bid-manager", ""))
    sections: list[tuple[str, str]] = []

    if (overview := _overview(final)):
        sections.append(("Tender at a glance", overview))

    decision = find_section(final, r"GO\s*/\s*NO.?GO|DECISION")
    if decision:
        value = re.split(r":", decision[0], maxsplit=1)[-1].strip() if ":" in decision[0] else ""
        value = re.sub(r"[^\w\s/().,'-]+", "", value).strip()  # drop status emoji such as ⚠️
        # The statement plus the MD's reasons. Numbered lists (conditions to
        # proceed) are left out because Next steps already covers them, as are
        # lead-ins such as "Proceed only if the following:".
        lines = [line.strip() for line in decision[1].split("\n") if line.strip()
                 and not re.fullmatch(r"(?:-{3,}|_{3,}|\*{3,})", line.strip())]
        statement = [line for line in lines if not re.match(r"^(?:[-*]|\d+\.)\s+", line)
                     and not line.endswith(":")][:1]
        reasons = [line for line in lines if re.match(r"^[-*]\s+", line)][:4]
        statement = [re.sub(r"^\**(?:Decision|Rationale)\**\s*:\s*\**\s*", "", line) for line in statement]
        body = ([f"**{value}**"] if value else []) + statement
        if reasons:
            body += ["**Why**"] + reasons
        sections.append(("Decision", "\n".join(body)))
    elif (fallback := find_section(manager, r"^Decision")):
        sections.append(("Decision", fallback[1]))

    if (deadlines := find_section(manager, r"Deadline")):
        sections.append(("Deadlines", deadlines[1]))

    if (eligibility := find_section(manager, r"Eligib")):
        sections.append(("Eligibility gaps", _eligibility_gaps(eligibility[1])))

    if (quote := find_section(final, r"RECOMMENDED QUOTE|QUOTE")):
        # Only the quote itself: its "required inputs" list repeats the
        # eligibility gaps shown above.
        value = next((line.strip() for line in quote[1].split("\n")
                      if line.strip() and not re.match(r"^\s*(?:[-*]|\d+\.)\s+", line)), "")
        if value:
            if re.search(r"NOT CALCULABLE", value, re.I):
                value += "\nIt can be priced once the eligibility gaps above are closed."
            sections.append(("Quote", value))

    risks = find_section(final, r"CRITICAL RISKS|RISKS") or find_section(manager, r"Risk")
    if risks:
        sections.append(("Top risks", _first_items(risks[1], SUMMARY_RISKS)))

    actions = find_section(final, r"ACTION ITEMS|NEXT STEPS") or find_section(manager, r"Action plan")
    if actions:
        sections.append(("Next steps", _first_items(actions[1], SUMMARY_ACTIONS)))

    return [(title, body) for title, body in sections if body.strip()]


TENDER_BRIEF_KEY = "tender-brief"

_SOURCE_CITATION = re.compile(r"\[Source:\s*[^\]\n]*?(?:,\s*page\s*(\d+))?\s*\]", re.I)


def compact_citations(text: str) -> str:
    """"[Source: Long file name.pdf, page 14]" -> "[p.14]"; a bare file citation is dropped.

    The brief cites every point, and the full file name on each line made a
    short brief long without adding information.
    """
    text = _SOURCE_CITATION.sub(lambda m: f"[p.{m.group(1)}]" if m.group(1) else "", text)
    text = re.sub(r"\[(?:Page|Pg\.?)\s*(\d+)\]", r"[p.\1]", text, flags=re.I)
    return re.sub(r"[ \t]+(?=\n|$)", "", re.sub(r"[ \t]{2,}", " ", text))
BID_ASSESSMENT_TITLE = "10. Our Bid Assessment"
# Summary sections the brief's own sections 1 and 2 already state.
BRIEF_COVERS = {"Tender at a glance", "Deadlines"}


def brief_sections(markdown: str) -> list[tuple[str, str]]:
    """Split the Tender Brief into its "##" sections.

    Only level-2 headings start a section: appendices use "###" sub-headings
    inside section 8, and those must stay with their section. Any preamble
    before the first "##" heading is dropped.
    """
    sections: list[tuple[str, list[str]]] = []
    for line in (markdown or "").replace("\r\n", "\n").split("\n"):
        heading = re.match(r"^\s*##\s+(.+?)\s*#*\s*$", line)
        if heading:
            sections.append((heading.group(1).replace("**", "").strip(), []))
        elif sections:
            sections[-1][1].append(line)
    return [(title, "\n".join(body).strip() or "Not stated in the tender") for title, body in sections]


def brief_has_decision(brief: list[tuple[str, str]]) -> bool:
    """True when the brief itself has the "Final Bid Recommendation" section."""
    return any(re.search(r"final bid recommendation", title, re.I) for title, _ in brief)


def without_self_check(final: str) -> str:
    # The quality-gate rewrite is an internal self-check, not bid content.
    return re.split(r"\n#{1,4}\s*\**QUALITY-GATE", final, maxsplit=1)[0]


def is_discrepancy_section(title: str) -> bool:
    return bool(re.search(r"discrepanc|contradict|conflict", title, re.I))


def build_pdf(bid: Bid, full: bool = False) -> str:
    from fpdf import FPDF

    pipeline = {}
    try:
        pipeline = json.loads(bid.pipeline_result or "{}")
    except Exception:
        pass

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # ── Cover ──────────────────────────────────────────────────────────────
    pdf.set_fill_color(30, 30, 30)
    pdf.rect(0, 0, 210, 36, 'F')
    pdf.set_y(8)
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 10, "TENDER ANALYST AI", align="C", ln=True)
    pdf.set_font("Helvetica", "", 10)
    brief = brief_sections(compact_citations(str(pipeline.get(TENDER_BRIEF_KEY) or "")))
    show_brief = bool(brief) and not full
    pdf.cell(0, 6, "Full Bid Report" if full else ("Tender Brief" if show_brief else "Bid Summary"),
             align="C", ln=True)
    pdf.set_text_color(180, 180, 180)
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(0, 6, f"Generated: {report_generated_timestamp()}", align="C", ln=True)

    pdf.set_y(44)
    pdf.set_text_color(30, 30, 30)
    pdf.set_font("Helvetica", "B", 14)
    safe_title = (bid.tender_name or "").encode('latin-1', errors='replace').decode('latin-1')
    pdf.multi_cell(0, 8, safe_title, align="L")

    # meta row
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.set_x(pdf.l_margin)
    meta = []
    if bid.department: meta.append(f"Dept: {bid.department}")
    if bid.portal: meta.append(f"Portal: {bid.portal}")
    if bid.reference_no: meta.append(f"Ref: {bid.reference_no}")
    if bid.submission_deadline: meta.append(f"Deadline: {bid.submission_deadline}")
    if meta:
        pdf.cell(0, 6, "  |  ".join(meta), ln=True)

    # recommended quote box
    final_report = str(pipeline.get("final", ""))
    quote_withheld = "NOT CALCULABLE FROM SUPPLIED EVIDENCE" in final_report.upper()
    if bid.recommended_quote and not quote_withheld:
        pdf.set_y(pdf.get_y() + 6)
        pdf.set_fill_color(240, 248, 240)
        pdf.set_draw_color(100, 180, 100)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(30, 30, 30)
        quote_str = (bid.recommended_quote or "").replace('₹', 'Rs.')
        confidence = f"   |   Confidence: {bid.bid_confidence}" if bid.bid_confidence else ""
        pdf.cell(0, 12, f"  RECOMMENDED QUOTE: {quote_str}{confidence}", border=1, fill=True, ln=True)
    elif quote_withheld:
        pdf.set_y(pdf.get_y() + 6)
        pdf.set_fill_color(255, 248, 230)
        pdf.set_draw_color(220, 160, 50)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 12, "  QUOTE STATUS: NOT CALCULABLE FROM SUPPLIED EVIDENCE", border=1, fill=True, ln=True)

    pdf.set_y(pdf.get_y() + 4)

    def safe_str(s: str) -> str:
        return strip_markdown(s)

    def section_header(title: str, alert: bool = False):
        # A single restrained corporate colour keeps multi-agent reports
        # consistent and avoids each section looking like a dashboard alert.
        # The one exception is the brief's discrepancies, which need action.
        if alert:
            pdf.set_fill_color(217, 119, 6)
        else:
            pdf.set_fill_color(30, 41, 59)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_x(pdf.l_margin)
        pdf.cell(0, 7, f"  {safe_str(title)}", fill=True, ln=True)
        pdf.set_text_color(30, 30, 30)
        pdf.set_y(pdf.get_y() + 1.5)

    def render_brief():
        for title, body in brief:
            if pdf.get_y() > pdf.page_break_trigger - 25:
                # Never leave a section bar alone at the foot of a page.
                pdf.add_page()
            section_header(title, alert=is_discrepancy_section(title))
            render_markdown(pdf, body)
            pdf.set_y(pdf.get_y() + 3)

    # ── Summary (always first) ──────────────────────────────────────────────
    summary = summary_sections(pipeline)
    if quote_withheld or (bid.recommended_quote and not quote_withheld):
        # The cover box above already states the quote.
        summary = [(title, body) for title, body in summary if title != "Quote"]
    if show_brief:
        render_brief()
        # Our own decision closes the brief, in one section after the nine
        # tender sections. The brief already covers the tender overview and
        # its dates, so only our assessment is taken from the summary.
        # The ten-section brief carries the GO / NO-GO decision in its section
        # 9, so appending our assessment again would only duplicate it.
        assessment = [] if brief_has_decision(brief) else [
            (title, body) for title, body in summary if title not in BRIEF_COVERS]
        if not brief_has_decision(brief) and (assessment or pipeline.get("final")):
            section_header(BID_ASSESSMENT_TITLE)
            for title, body in assessment:
                render_markdown(pdf, f"### {title}")
                render_markdown(pdf, body)
                pdf.set_y(pdf.get_y() + 1.5)
            if not assessment:
                render_markdown(pdf, without_self_check(pipeline["final"]))
    else:
        for title, body in summary:
            section_header(title)
            render_markdown(pdf, body)
            pdf.set_y(pdf.get_y() + 1.5)
        if not summary and pipeline.get("final"):
            section_header("MD BRIEFING — FINAL RECOMMENDATION")
            render_markdown(pdf, pipeline["final"])

    if not full:
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(110, 110, 110)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 5, "AI-generated draft for human review. Each specialist's detailed working is in the Full report.")
    else:
        # ── Detailed reports (appendix) ─────────────────────────────────────
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(0, 10, "Appendix: detailed specialist reports", ln=True)
        pdf.set_y(pdf.get_y() + 2)
        if brief:
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(24, 38, 58)
            pdf.cell(0, 8, "Tender Brief", ln=True)
            render_brief()
            pdf.set_y(pdf.get_y() + 2)
        for agent_id in AGENT_ORDER:
            content = pipeline.get(agent_id, "")
            if not content:
                continue
            section_header(AGENT_NAMES[agent_id])
            render_markdown(pdf, content)
            pdf.set_y(pdf.get_y() + 4)
        final = pipeline.get("final", "")
        if final:
            section_header("MD BRIEFING — FINAL RECOMMENDATION")
            render_markdown(pdf, without_self_check(final))

    # save to temp
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(tmp.name)
    return tmp.name


@router.get("/bids/{bid_id}/export")
def export_bid(bid_id: int, full: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    bid = db.query(Bid).filter(Bid.id == bid_id, Bid.user_id == user.id).first()
    if not bid:
        raise HTTPException(status_code=404, detail="Bid not found")
    path = build_pdf(bid, full=full)
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', bid.tender_name)[:50]
    return FileResponse(
        path=path,
        filename=f"Bid_{safe_name}{'_Full' if full else ''}.pdf",
        media_type="application/pdf",
    )
