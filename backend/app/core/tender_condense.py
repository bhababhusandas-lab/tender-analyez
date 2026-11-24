"""Condense oversized tender text so the model reads the parts that matter.

A local model reads at most its context window (32k tokens for qwen3:8b) and
silently drops the rest. A real tender with its bid document and drawings is
often 100k+ tokens, so without this module the NIT facts, eligibility criteria
and penalties that sit after the first ~120k characters never reach the model.

When the input is over budget, each source document is split into page (or
~1,500-character paragraph) chunks, every chunk is scored against the topics a
bid analysis needs, and the best chunks per topic are kept first so every topic
is covered, then the rest of the budget is filled by score. Kept chunks stay in
their original order under their `--- SOURCE DOCUMENT` / `--- PAGE` markers so
citations still work. Bill-of-quantity rows are the lowest priority, except
lines carrying totals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ~90k characters is ~23-26k tokens of tender text, leaving room within a 32k
# context for the system prompt, task brief and the model's answer.
TENDER_CHAR_BUDGET = 90_000
CHUNK_CHARS = 1_500
# A page up to this size stays one chunk; larger pages are split by paragraph.
MAX_PAGE_CHUNK_CHARS = 2_600
PER_TOPIC_CHUNKS = 2
# Update sections of a re-analysis are always kept, up to this share of the budget.
PINNED_SHARE = 0.5
MIN_FILL_SCORE = 2.0

SOURCE_RE = re.compile(r"^--- (?:SOURCE DOCUMENT:\s*.+?|PASTED TENDER TEXT) ---\s*$", re.I)
PAGE_RE = re.compile(r"^--- PAGE\s+\d+\s*---\s*$", re.I)
SECTION_RE = re.compile(r"^=== .+ ===\s*$")
# Re-analysis sections that must survive condensation (this update, the user's note, their chat).
PINNED_SECTION_RE = re.compile(r"^=== (?:UPDATE\b|EARLIER DISCUSSION\b)", re.I)
# Earlier updates (corrigenda) outrank the original documents they amend.
BOOSTED_SECTION_RE = re.compile(r"^=== EARLIER UPDATE\b", re.I)

TOPICS: dict[str, tuple[str, ...]] = {
    "nit_key_dates": (
        r"notice\s+inviting", r"\bnit\b", r"last\s+date", r"closing\s+date", r"due\s+date",
        r"bid\s+submission", r"date\s+(?:and|&)\s+time", r"opening\s+of", r"\bopening\b",
        r"\d{1,2}[./-]\d{1,2}[./-]\d{4}",
    ),
    "emd_fees": (
        r"\be\.?m\.?d\b", r"earnest\s+money", r"bid\s+security", r"tender\s+fee", r"transaction\s+fee",
        r"processing\s+fee", r"cost\s+of\s+(?:tender|bid)\s+document", r"bank\s+guarantee", r"surety\s+bond",
    ),
    "eligibility": (
        r"eligib", r"qualif", r"similar\s+(?:nature\s+of\s+)?work", r"turnover", r"bid\s+capacity",
        r"\b2\s*A\s*N\b", r"liquid\s+assets", r"credit\s+facilit", r"net\s*worth", r"registration",
        r"special\s+class", r"joint\s+venture", r"\bJV\b", r"consortium", r"lead\s+member", r"experience", r"solvency",
    ),
    "key_personnel": (
        r"key\s+personnel", r"technical\s+personnel", r"\bpersonnel\b", r"\bengineers?\b",
        r"graduate", r"diploma", r"site\s+(?:engineer|in-?charge)", r"\bstaff\b",
    ),
    "equipment": (
        r"equipment", r"machinery", r"\bplant\b", r"hot\s+mix", r"paver", r"crusher", r"roller",
        r"batching", r"tipper", r"excavator",
    ),
    "scope": (
        r"scope\s+of\s+(?:the\s+)?work", r"name\s+of\s+(?:the\s+)?work", r"description\s+of\s+work",
        r"\blength\b", r"\bpackage\b", r"\bkm\b", r"carriageway", r"alignment", r"\bbridges?\b", r"culvert",
    ),
    "evaluation": (
        r"evaluat", r"\bL-?1\b", r"lowest", r"price\s+bid", r"technical\s+bid", r"financial\s+bid",
        r"reverse\s+auction", r"tender\s+premium", r"\bmarks\b", r"qualifying", r"percentage\s+(?:rate|quoted)", r"award",
    ),
    "payment_taxes": (
        r"payment", r"\bbills?\b", r"deduct", r"\bGST\b", r"\btax(?:es)?\b", r"\bTDS\b",
        r"mobili[sz]ation\s+advance", r"retention", r"price\s+(?:adjustment|variation)", r"escalation",
        r"security\s+deposit", r"additional\s+security", r"performance\s+(?:security|guarantee)",
    ),
    "penalties_ld_dlp": (
        r"penalt", r"liquidated\s+damages", r"\bL\.?D\.?\b", r"\bdelay", r"defects?\s+liability",
        r"\bDLP\b", r"terminat", r"forfeit", r"black-?list", r"compensation",
    ),
    "documents": (
        r"documents?\s+to\s+be\s+(?:uploaded|submitted|furnished)", r"scanned\s+cop", r"upload",
        r"certificate", r"affidavit", r"check-?\s?list", r"annexure", r"\bform\s+[a-z0-9]",
        r"attested", r"undertaking",
    ),
    "prebid_corrigendum": (
        r"pre[\s-]*bid", r"corrigend", r"addend", r"amendment", r"clarification", r"quer(?:y|ies)",
    ),
}
_TOPIC_RES = {topic: [re.compile(p, re.I) for p in patterns] for topic, patterns in TOPICS.items()}

_AMOUNT_RE = re.compile(r"(?:₹|\brs\.?|\binr\b)\s*\d|\d\s*(?:crores?|cr\b|lakhs?)", re.I)
_DATE_RE = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b")
_UNIT_RE = re.compile(
    r"\b(?:cum|cu\.?\s?m|sqm|sq\.?\s?m|rmt|r\.?m|each|nos?|mt|kg|ltr|per\s+month|rm|metre|m3|m2|km)\b", re.I,
)
_BOQ_HEADER_RE = re.compile(
    r"(?:quantity|qty)\W{0,40}(?:unit|uom)\W{0,40}rate|rate\s*\(inr\)\s*amount|subwork\s+name\s+specification", re.I,
)
_TOTAL_RE = re.compile(
    r"^\s*(?:grand\s+|sub-?\s?)?total(?:\s+(?:amount|cost|value))?\s*(?:\([^)\n]{0,12}\))?\s*[:=\-]?\s*(?:rs\.?|₹|inr)?\s*\d",
    re.I,
)


@dataclass
class Chunk:
    index: int
    source: str | None      # the `--- SOURCE DOCUMENT` header line
    section: str | None     # the `=== ... ===` header line (re-analysis inputs)
    page: str | None        # the `--- PAGE n ---` marker line
    text: str
    pinned: bool = False
    topic_scores: dict[str, float] = field(default_factory=dict)
    score: float = 0.0
    boq: bool = False
    totals: str = ""        # total lines of a BOQ chunk, kept when the chunk is not

    @property
    def cost(self) -> int:
        return len(self.text) + 1


def _split_long(text: str, limit: int = CHUNK_CHARS) -> list[str]:
    """Split text into ~`limit`-character pieces at paragraph, then line, boundaries."""
    paragraphs = re.split(r"\n\s*\n", text)
    pieces: list[str] = []
    current = ""
    for paragraph in paragraphs:
        units = [paragraph] if len(paragraph) <= limit else paragraph.split("\n")
        for unit in units:
            while len(unit) > limit * 2:  # a single enormous line
                pieces.append(unit[:limit])
                unit = unit[limit:]
            if current and len(current) + len(unit) + 1 > limit:
                pieces.append(current)
                current = unit
            else:
                current = f"{current}\n{unit}" if current else unit
    if current.strip():
        if pieces and len(current) < 400:
            pieces[-1] = f"{pieces[-1]}\n{current}"  # no tiny tail chunks
        else:
            pieces.append(current)
    return [piece for piece in pieces if piece.strip()]


def _chunks(raw_text: str) -> list[Chunk]:
    """Split into page/paragraph chunks that remember their document headers."""
    chunks: list[Chunk] = []
    source: str | None = None
    section: str | None = None
    page: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        text = "\n".join(buffer).strip("\n")
        buffer.clear()
        if not text.strip():
            return
        pinned = bool(section and PINNED_SECTION_RE.match(section))
        pieces = [text] if len(text) <= MAX_PAGE_CHUNK_CHARS else _split_long(text)
        for piece in pieces:
            chunks.append(Chunk(len(chunks), source, section, page, piece, pinned))

    for line in raw_text.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if SECTION_RE.match(stripped) and not stripped.startswith("=== DETERMINISTIC"):
            flush()
            section, source, page = stripped, None, None
        elif SOURCE_RE.match(stripped):
            flush()
            source, page = stripped, None
        elif PAGE_RE.match(stripped):
            flush()
            page = stripped
        else:
            buffer.append(line)
    flush()
    return chunks


def _is_boq(text: str) -> bool:
    """Long runs of item rows: quantities, units and rates, little prose."""
    lines = [line for line in text.split("\n") if line.strip()]
    if len(lines) < 6:
        return False
    rowish = 0
    for line in lines:
        numbers = re.findall(r"\d+(?:[.,]\d+)*", line)
        if len(numbers) >= 2 and (_UNIT_RE.search(line) or len(numbers) >= 3):
            rowish += 1
    if rowish / len(lines) >= 0.3:
        return True
    # A BOQ table header ("Quantity UOM Rate Amount") marks the chunk as BOQ
    # unless substantial other text comes before it.
    header = _BOQ_HEADER_RE.search(text)
    return header is not None and header.start() < 400


def _score(chunk: Chunk) -> None:
    text = chunk.text
    for topic, patterns in _TOPIC_RES.items():
        hits = 0.0
        for pattern in patterns:
            count = len(pattern.findall(text))
            if count:
                hits += 1 + min(count - 1, 3) * 0.25  # distinct keywords matter most
        chunk.topic_scores[topic] = hits
    score = sum(min(hits, 6.0) for hits in chunk.topic_scores.values())
    if _AMOUNT_RE.search(text):
        score += 1.5
    if _DATE_RE.search(text):
        score += 1.0
    # Denser chunks are worth more per character.
    score *= min(1.3, max(0.5, CHUNK_CHARS / max(len(text), 1_000)))
    if chunk.section and BOOSTED_SECTION_RE.match(chunk.section):
        score *= 2
    chunk.score = score
    if _is_boq(text):
        _mark_boq(chunk)


def _mark_boq(chunk: Chunk) -> None:
    if not chunk.boq:
        chunk.boq = True
        chunk.score *= 0.05
        chunk.topic_scores = {topic: hits * 0.05 for topic, hits in chunk.topic_scores.items()}
    chunk.totals = "\n".join(
        line for line in chunk.text.split("\n") if _TOTAL_RE.search(line) and re.search(r"\d{3,}", line)
    )[:600]


def _smooth_boq(chunks: list[Chunk]) -> None:
    """Pieces of a BOQ page, and chunks between two BOQ chunks, that carry item rows are BOQ too."""
    boq_pages = {(c.source, c.page) for c in chunks if c.boq and c.page}
    for chunk in chunks:
        if (not chunk.boq and chunk.page and (chunk.source, chunk.page) in boq_pages
                and not _BOQ_HEADER_RE.search(chunk.text) and re.search(r"\d+\.\d{2}", chunk.text)):
            _mark_boq(chunk)
    for before, chunk, after in zip(chunks, chunks[1:], chunks[2:]):
        if (not chunk.boq and before.boq and after.boq and before.source == chunk.source == after.source
                and _UNIT_RE.search(chunk.text) and re.search(r"\d+\.\d{2}", chunk.text)):
            _mark_boq(chunk)


def _render(chunks: list[Chunk], selected: set[int], use_totals: set[int],
            note: str) -> str:
    out: list[str] = [note]
    last_source = last_section = last_page = None
    gap = False
    started = False
    for chunk in chunks:
        if chunk.index not in selected and chunk.index not in use_totals:
            gap = True
            continue
        if chunk.section != last_section and chunk.section:
            out.append(chunk.section)
            last_source = last_page = None
        if chunk.source != last_source and chunk.source:
            out.append(chunk.source)
            last_page = None
        if gap and started:
            out.append("[… passages omitted …]")
        if chunk.page and chunk.page != last_page:
            out.append(chunk.page)
        if chunk.index in selected:
            out.append(chunk.text)
        else:
            out.append(f"[bill-of-quantity rows omitted; totals:]\n{chunk.totals}")
        last_section, last_source, last_page = chunk.section, chunk.source, chunk.page
        gap = False
        started = True
    return "\n".join(out)


def condense_tender_text(raw_text: str, budget: int = TENDER_CHAR_BUDGET) -> str:
    """Return `raw_text` unchanged when it fits `budget`, otherwise a condensed copy.

    The condensed copy starts with a one-line note saying how much was omitted.
    """
    if len(raw_text) <= budget:
        return raw_text
    chunks = _chunks(raw_text)
    for chunk in chunks:
        _score(chunk)
    _smooth_boq(chunks)

    note_reserve = 260
    headers = {c.source for c in chunks if c.source} | {c.section for c in chunks if c.section}
    overhead = note_reserve + sum(len(h) + 1 for h in headers)
    available = budget - overhead
    selected: set[int] = set()
    used = 0

    def take(chunk: Chunk) -> bool:
        nonlocal used
        # Room for a page marker and an omission marker around the chunk.
        cost = chunk.cost + (len(chunk.page) + 1 if chunk.page else 0) + 26
        if chunk.index in selected or used + cost > available:
            return False
        selected.add(chunk.index)
        used += cost
        return True

    # BOQ totals are small and worth keeping; reserve room for them up front.
    totals_reserve = sum(len(c.totals) + 40 for c in chunks if c.boq and c.totals)
    available -= min(totals_reserve, available // 10)

    # 1. Re-analysis updates and the user's statements come first, as written.
    pinned_limit = available * PINNED_SHARE
    for chunk in chunks:
        if chunk.pinned and used + chunk.cost <= pinned_limit:
            take(chunk)

    # 2. Coverage: the best chunks for every topic, round-robin by rank.
    ranked = {
        topic: sorted((c for c in chunks if c.topic_scores.get(topic, 0) >= 1 and not c.boq),
                      key=lambda c: (c.topic_scores[topic] + 0.2 * c.score), reverse=True)
        for topic in TOPICS
    }
    for rank in range(PER_TOPIC_CHUNKS):
        for topic in TOPICS:
            candidates = [c for c in ranked[topic] if c.index not in selected]
            if candidates:
                take(candidates[0])

    # 3. Fill the rest of the budget by overall score (BOQ rows last); chunks
    # with nothing a bid analysis needs (page footers, stray rows) are skipped.
    for chunk in sorted(chunks, key=lambda c: c.score, reverse=True):
        if chunk.score >= MIN_FILL_SCORE and len(chunk.text.strip()) >= 200:
            take(chunk)

    # 4. BOQ chunks that did not make it keep their total lines.
    available += min(totals_reserve, (budget - overhead) // 10)
    use_totals: set[int] = set()
    for chunk in chunks:
        if chunk.boq and chunk.totals and chunk.index not in selected:
            cost = len(chunk.totals) + 40
            if used + cost <= available:
                use_totals.add(chunk.index)
                used += cost

    kept_chars = sum(len(c.text) for c in chunks if c.index in selected)
    total_chars = sum(len(c.text) for c in chunks)
    omitted = len(chunks) - len(selected)
    note = (
        f"[Condensed input: the tender is {len(raw_text):,} characters, more than the model can read. Kept {kept_chars:,} characters ({len(selected)} of {len(chunks)} passages) chosen "
        f"for NIT dates, fees, eligibility, personnel, equipment, scope, evaluation, payment, penalties and "
        f"documents; omitted {omitted} passages ({total_chars - kept_chars:,} characters), mostly "
        f"bill-of-quantity rows and general conditions. Do not assume omitted text is absent from the tender.]"
    )
    text = _render(chunks, selected, use_totals, note)
    # Safety net: never exceed the budget, whatever the estimate above missed.
    order = sorted((c for c in chunks if c.index in selected and not c.pinned), key=lambda c: c.score)
    while len(text) > budget and (order or use_totals):
        if use_totals:
            use_totals.pop()
        else:
            selected.discard(order.pop(0).index)
        text = _render(chunks, selected, use_totals, note)
    return text


def build_model_input(raw_text: str, evidence_block: str = "", budget: int = TENDER_CHAR_BUDGET) -> str:
    """The AI input: the deterministic evidence block first, then the tender within budget."""
    if not evidence_block:
        return condense_tender_text(raw_text, budget).strip()
    body = condense_tender_text(raw_text, max(budget - len(evidence_block) - 2, budget // 2))
    return f"{evidence_block}\n\n{body}".strip()


# The final MD step reads the tender AND every specialist's report, so both
# are bounded to fit the model window together (~32k tokens).
FINAL_TENDER_BUDGET = 35_000
FINAL_TEAM_BUDGET = 55_000
_EVIDENCE_END = "=== END DETERMINISTIC METADATA EVIDENCE ==="


def condense_for_final(tender_text: str, reports: list[tuple[str, str]]) -> tuple[str, str]:
    """Return (tender part, team part) sized for the final briefing.

    The deterministic evidence block is always kept whole at the top; the rest
    of the tender is condensed. Each report gets an equal share of the team
    budget and is cut at a line boundary with a visible marker.
    """
    head, rest = "", tender_text
    if _EVIDENCE_END in tender_text:
        cut = tender_text.index(_EVIDENCE_END) + len(_EVIDENCE_END)
        head, rest = tender_text[:cut], tender_text[cut:]
    remaining = max(5_000, FINAL_TENDER_BUDGET - len(head))
    tender_part = (head + "\n\n" + condense_tender_text(rest.strip(), remaining)).strip() if len(rest) > remaining else tender_text

    share = FINAL_TEAM_BUDGET // max(1, len(reports))
    parts = []
    for name, content in reports:
        content = content or "N/A"
        if len(content) > share:
            content = content[:share].rsplit("\n", 1)[0] + "\n[… report shortened for the final briefing]"
        parts.append(f"=== {name} ===\n{content}")
    return tender_part, "\n\n".join(parts)
