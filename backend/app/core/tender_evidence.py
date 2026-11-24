"""Deterministic extraction of high-value tender metadata.

The LLM still writes the narrative report, but these fields are collected before
the model runs so important identifiers, money values and dates cannot disappear
inside a long tender document.  Every candidate retains its source document and
page marker for human verification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Evidence:
    field: str
    value: str
    source: str
    page: str | None
    excerpt: str


# A label is followed by an optional parenthetical unit such as "(₹)" or
# "(IN FIGURES & WORDS)", an optional separator (colon, dash, pipe or tab) and
# the rest of the line. The rest may be empty when the value sits on a later
# line, as it does in many NIT tables.
_REST = r"(?:[ \t]*\([^)\n]{0,40}\))?[ \t]*(?:[:#|\t]|[-–](?!\d))?[ \t]*([^\n]*)"


def _label(pattern: str) -> str:
    return f"(?:{pattern}){_REST}"


FIELD_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Tender Title", (
        _label(r"tender\s+title|name\s+of\s+(?:the\s+)?work(?:\s+given\s+in\s+the\s+estimate)?|title\s+of\s+(?:the\s+)?tender"),
        r"(?:project|subject)\s*[:\-]\s*([^\n]*)",
    )),
    ("Issuing Department / Organisation", (
        _label(r"issuing\s+(?:department|authority|organisation|organization)|department\s*/\s*organisation|procuring\s+(?:entity|authority)|organisation\s+name|organization\s+name"),
    )),
    ("Tender Reference / NIT Number", (
        _label(r"tender\s*(?:reference|ref\.?|id)(?:\s*/\s*nit\s*(?:number|no\.?|id))?|nit\s*(?:number|no\.?|id)|rfp\s*(?:number|no\.?|id)|bid\s*(?:number|no\.?|id)"),
    )),
    ("Estimated Contract Value", (
        _label(r"estimated?\s+(?:contract|tender)\s+value(?:\s+of\s+(?:the\s+)?work)?(?:\s+put\s+to\s+tender)?|estimated\s+(?:cost|value)|tender\s+value|contract\s+value"),
        # "ECV" is common in prose ("1% of ECV"), so only a separated label counts.
        r"\be\.?c\.?v\b\.?(?:\s+put\s+to\s+tender)?\s*[:|\t]\s*([^\n]*)",
    )),
    # Kept separate so a fee can never be read as the contract value.
    ("Application / Tender Fee", (
        _label(r"application\s+fee|tender\s+(?:document\s+)?fee|(?:tender|bid)\s+processing\s+fee|cost\s+of\s+(?:the\s+)?(?:tender|bid)\s+documents?|tender\s+cost|document\s+fee"),
    )),
    ("EMD Amount", (
        _label(r"(?:earnest\s+money\s+deposit|\be\.?m\.?d\b\.?|bid\s+security)(?:\s+amount)?"),
    )),
    ("Bid Submission Deadline", (
        _label(r"bid\s+(?:document\s+)?submission\s+(?:deadline|end\s+date|last\s+date)|submission\s+(?:deadline|closing\s+date)|last\s+date(?:\s+and\s+time)?\s+(?:for|of)\s+(?:the\s+)?(?:bid\s+)?submission(?:\s+of\s+(?:the\s+)?(?:tenders?|bids?))?|bid\s+closes?|closing\s+date(?:\s+and\s+time)?(?!\s+[^\n:|]{0,60}?\bopening\b)"),
    )),
    ("Bid Opening Date", (
        _label(r"bid\s+opening(?:\s+date(?:\s+and\s+time)?)?|opening\s+date(?:\s+and\s+time)?|date\s+(?:and\s+time\s+)?of\s+opening(?:\s+of\s+(?:the\s+)?(?:tenders?|bids?))?"),
    )),
    ("Technical Bid Opening", (
        _label(r"(?:technical\s+bid\s+opening|opening\s+of\s+(?:the\s+)?technical\s+bids?)(?:\s+date)?(?:\s+(?:and|&)\s+time)?|technical\s+bids?(?=[ \t]*(?:[:|\t]|$))"),
    )),
    ("Pre-bid Meeting", (
        _label(r"pre[\s-]*bid(?:\s+(?:meeting|conference))?(?:\s+(?:date|venue))?(?:\s+(?:and|&)\s+time)?"),
    )),
    ("Contract Duration / Period", (
        _label(r"contract\s+duration(?:\s*/\s*period)?|contract\s+period|completion\s+period|(?:stipulated\s+)?period\s+of\s+completion(?:\s+of\s+(?:the\s+)?work)?|time\s+(?:allowed\s+)?for\s+completion|period\s+of\s+contract|delivery\s+period|project\s+duration"),
        r"(?:the\s+)?engagement\s+is\s+expected\s+to\s+run\s+(?:over|for)\s+((?:approximately\s+|about\s+)?\d+\s+(?:days?|weeks?|months?|years?))",
        r"(?:delivery\s+and\s+installation\s+must\s+be\s+completed\s+within)\s+([^\n|.]{2,120})",
    )),
    ("Procurement Portal", (
        _label(r"procurement\s+portal|e-?procurement\s+(?:portal|website)|portal\s+(?:url|website|address)"),
    )),
    ("Location / State", (
        _label(r"location\s*/\s*state|place\s+of\s+(?:work|delivery)|project\s+location|work\s+location"),
    )),
)

DATE_FIELDS = frozenset({"Bid Submission Deadline", "Bid Opening Date", "Technical Bid Opening", "Pre-bid Meeting"})
AMOUNT_FIELDS = frozenset({
    "Estimated Contract Value", "EMD Amount", "Application / Tender Fee",
    "Similar Work Value", "Liquid Assets / Credit Facility",
})
LIST_FIELDS = frozenset({"Key Personnel", "Key Equipment", "Mandatory Documents"})
# Facts assembled from the whole document rather than one label/value row.
DOCUMENT_FIELDS = (
    "Consortium / JV Conditions", "Technical Evaluation Marks", "Mandatory Documents", "Hard Copy Submission",
)
FORMULA_FIELDS = frozenset({"Bid Capacity Formula"})
DURATION_FIELDS = frozenset({"Contract Duration / Period"})
TEXT_FIELDS = frozenset({"Tender Title"})
REFERENCE_FIELDS = frozenset({"Tender Reference / NIT Number"})

SOURCE_RE = re.compile(r"^--- SOURCE DOCUMENT:\s*(.+?)\s*---$", re.I)
PAGE_RE = re.compile(r"^--- PAGE\s+(\d+)\s*---$", re.I)

_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
DATE_RE = re.compile(
    r"(?<!\d)(?:\d{1,2}[./-]\d{1,2}[./-](?:\d{4}|\d{2})(?!\d)"
    rf"|\d{{1,2}}(?:st|nd|rd|th)?[\s-]+{_MONTH}[\s,-]+\d{{4}}"
    rf"|{_MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}})",
    re.I,
)
TIME_RE = re.compile(
    r"(?<![\d.])(?:\d{1,2}(?:[.:]\d{2})?\s*(?:[ap]\.?\s?m\b\.?|hrs\b\.?|hours\b)"
    r"|\d{1,2}[.:]\d{2}(?!\d)(?:\s*(?:hrs\b\.?|hours\b|ist\b))?)(?:\s*ist\b)?",
    re.I,
)
_DATE_TIME_GAP = re.compile(r"[ \t]*(?:(?:@|at|,|by|upto|up\s+to|on|-|–)[ \t]*)*", re.I)
AMOUNT_RE = re.compile(
    r"(?:(?:₹|\brs\b\.?|\binr\b)\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:crores?|cr\b\.?|lakhs?|lacs?))?"
    r"|(?<![\d.,])\d[\d,]*(?:\.\d+)?\s*(?:crores?|cr\b\.?|lakhs?|lacs?)"
    r"|^\d[\d,]{4,}(?:\.\d+)?(?:\s*/-)?\s*$)",
    re.I,
)
_NUMBER_WORDS = r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|eighteen|twenty|twenty[\s-]four|thirty|thirty[\s-]six|forty[\s-]eight)"
DURATION_RE = re.compile(
    r"^(?:(?:approximately|approx\.?|about|within|upto|up\s+to|of|a\s+period\s+of)\s+)*"
    rf"(?:{_NUMBER_WORDS}\s*\(\s*\d+\s*\)|\d+(?:\.\d+)?)\s*(?:\(\s*{_NUMBER_WORDS}\s*\)\s*)?"
    r"(?:calendar\s+|working\s+)?(?:days?|weeks?|months?|years?)\b",
    re.I,
)
# Words a truncated label fragment tends to end on ("Construction of ... from").
_DANGLING = re.compile(r"(?:\b(?:from|to|of|and|for|the|at|near|in|on|with|by|a|an)|[-–,&(])$", re.I)
_TRIVIAL = {"no", "yes", "of", "the", "nil", "na", "n/a", "not specified", "not applicable", "-", "tbd", "as above"}
# A new NIT row ("7) ...", "8. Date ...") ends a value search.
_NEW_ITEM = re.compile(r"^\s*(?:\(?\d{1,2}\)\s*\S|\d{1,2}\.\s+[A-Za-z])")
_SUB_ITEM = re.compile(r"^\s*\(?(?:[a-h]|i{1,3}|iv|v|vi{1,3})\)\s*\S.{0,40}$", re.I)
_ALLOWED_PREFIX = re.compile(r"(?:[-*•|]|\d+[.)]|\(?(?:[a-z]|[ivx]{1,5})[.)])", re.I)


def _clean(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" \t:;-–—|")
    # Stop at common same-line labels in flattened PDF tables.
    value = re.split(
        r"\s{2,}(?=(?:tender|nit|emd|bid|estimated|opening|closing|submission|contract)\b)",
        value,
        maxsplit=1,
        flags=re.I,
    )[0]
    return value[:240].strip()


def _cell(value: str) -> str:
    """The first table cell of an inline value: drop separators, stop at the next | or tab."""
    value = re.sub(r"^[\s:;|#\-–—]+", "", value)
    value = re.split(r"\s*\|\s*|\t", value, maxsplit=1)[0]
    return _clean(value)


def _date_value(text: str, window: int = 40) -> str | None:
    match = DATE_RE.search(text)
    if not match or match.start() > window:
        return None
    start, end = match.start(), match.end()
    gap = _DATE_TIME_GAP.match(text, end)
    time = TIME_RE.match(text, gap.end()) if gap else None
    if time:
        end = time.end()
    else:
        # "15:00 hrs on 30.09.2026": a time just before the date.
        before = list(TIME_RE.finditer(text[:start]))
        if before and start - before[-1].end() <= 8 and before[-1].start() <= window:
            start = before[-1].start()
    return _clean(text[start:end])


def _amount_value(text: str, window: int = 30) -> str | None:
    match = AMOUNT_RE.search(text.strip())
    if not match or match.start() > window:
        return None
    return _clean(re.sub(r"\s*/-\s*$", "", match.group(0)))


# Words that mark an amount as a fee, deposit, cap or percentage rather than
# the value of the contract ("0.04% of ECV with a cap of Rs.10,000").
_NOT_CONTRACT_VALUE = re.compile(
    r"\b(?:fees?|charges?|corpus\s+fund|earnest|e\.?m\.?d|bid\s+security|security\s+deposit|"
    r"cost\s+of\s+(?:the\s+)?(?:tender|bid)|tender\s+cost|non[\s-]*refundable|cap\s+of|penalt\w+|"
    r"turnover|transaction|processing)\b|\d\s*%|\bper\s*cent",
    re.I,
)


def _contract_value(text: str, context: str = "") -> str | None:
    """An amount that directly follows a contract-value label.

    A fee, EMD, cap or percentage must never be recorded as the contract value,
    so the amount has to start the value cell ("Rs. 5 Cr", "approx. Rs. 5 Cr")
    and neither the label's line nor the words before the amount may speak of
    a fee. A cell starting with ")" means the label closed a parenthetical in
    running prose ("... of ECV (estimated\ncontract value) with a cap of ...").
    """
    text = text.strip()
    match = AMOUNT_RE.search(text)
    if not match:
        return None
    lead = text[:match.start()]
    if lead.lstrip().startswith(")") or len(re.findall(r"[A-Za-z]+", lead)) > 2:
        return None
    if _NOT_CONTRACT_VALUE.search(f"{context} {lead}"):
        return None
    return _clean(re.sub(r"\s*/-\s*$", "", match.group(0)))


def _dehyphenate(text: str) -> str:
    """Rejoin words a PDF broke across lines ("Sub-\nmission" -> "Submission")."""
    return re.sub(r"(?<=[a-z])-[ \t]*\n[ \t]*(?=[a-z])", "", text)


def _duration_value(text: str) -> str | None:
    text = _clean(text)
    return text[:120] if DURATION_RE.match(text) else None


def _text_value(text: str) -> str | None:
    text = _clean(text)
    if len(text) < 12 or len(text.split()) < 3 or _DANGLING.search(text) or text.casefold() in _TRIVIAL:
        return None
    return text


def _reference_value(text: str) -> str | None:
    text = _clean(text)
    if len(text) < 3 or not re.search(r"\d", text) or text.casefold() in _TRIVIAL:
        return None
    return text[:100]


def _plain_value(text: str) -> str | None:
    text = _clean(text)
    if len(text) < 3 or not re.search(r"[a-z]", text, re.I) or text.casefold() in _TRIVIAL:
        return None
    if _DANGLING.search(text) and 1 < len(text.split()) <= 4:
        return None
    return text


def validate_value(field: str, text: str, context: str = "") -> str | None:
    """Return the value to record for `field`, or None when `text` is not one.

    `context` is the text of the label's line up to the value.
    """
    if field in DATE_FIELDS:
        return _date_value(text)
    if field == "Estimated Contract Value":
        return _contract_value(text, context)
    if field in AMOUNT_FIELDS:
        return _amount_value(text)
    if field in DURATION_FIELDS:
        return _duration_value(text)
    if field in TEXT_FIELDS:
        return _text_value(text)
    if field in REFERENCE_FIELDS:
        return _reference_value(text)
    return _plain_value(text)


def _starts_with_value(field: str, line: str) -> str | None:
    """A continuation line counts only when it *is* the value, not prose mentioning one."""
    stripped = line.strip()
    cell = stripped.startswith((":", "|"))
    body = re.sub(r"^[\s:;|\-–]+", "", stripped)
    if not body:
        return None
    if field in DATE_FIELDS:
        value = _date_value(body, window=0 if not cell else 25)
    elif field in AMOUNT_FIELDS:
        value = _amount_value(body, window=0 if not cell else 10)
    else:
        value = validate_value(field, body)
    if value and (cell or len(body) <= 60):
        return value
    return None


def _position_in_label_list(lines: list[str], index: int) -> int:
    """For "a) Technical Bid / b) Pre-Bid" rows followed by their values, this row's position."""
    if not _SUB_ITEM.match(lines[index]):
        return 0
    position = 0
    for previous in reversed(lines[:index]):
        if not _SUB_ITEM.match(previous) or DATE_RE.search(previous):
            break
        position += 1
    return position


def _continued_title(start: str, following: list[str]) -> str:
    title = start
    if title and not (_DANGLING.search(title) or title.count("(") > title.count(")")):
        return title
    for line in following[:6]:
        stripped = line.strip()
        if not stripped or _NEW_ITEM.match(line):
            break
        unbalanced = title.count("(") > title.count(")")
        if not (_DANGLING.search(title) or unbalanced or not title or stripped[0].islower() or stripped[0] == "("):
            break
        title = f"{title} {stripped}".strip()
        if len(title) > 240:
            break
    return title


def _value_after_label(field: str, lines: list[str], label_index: int, inline: str) -> tuple[str | None, str]:
    """Find the value for a label whose own line did not carry a valid one."""
    following = lines[label_index + 1:label_index + 11]
    if field in TEXT_FIELDS:
        title = _text_value(_continued_title(inline, following))
        return title, ""
    position = _position_in_label_list(lines, label_index)
    values: list[tuple[str, str]] = []
    for line in following:
        stripped = line.strip()
        if not stripped or re.fullmatch(r"[:|\s]+", stripped):
            continue
        if _NEW_ITEM.match(line):
            break
        if _SUB_ITEM.match(line) and not DATE_RE.search(line) and not AMOUNT_RE.search(line):
            continue
        value = _starts_with_value(field, line)
        if value:
            values.append((value, stripped))
            if len(values) > position:
                break
        elif values:
            break
    if len(values) > position:
        return values[position]
    return None, ""


def _label_matches(pattern: str, body: str):
    """Matches of `pattern` that sit where a label can: at the start of a line.

    Unlike ``re.finditer``, a rejected match does not hide an overlapping one
    that starts later ("Bid Submission\nClosing Date" -> "Closing Date").
    """
    compiled = re.compile(pattern, re.I | re.M)
    position = 0
    while True:
        match = compiled.search(body, position)
        if not match:
            return
        line_start = body.rfind("\n", 0, match.start()) + 1
        prefix = body[line_start:match.start()].strip()
        label_text = body[match.start():match.start(1)]
        # Labels must begin a line (apart from bullets/row numbers). This
        # prevents prose such as "during the contract period" from being
        # mistaken for a metadata field. A label wrapped over lines is an NIT
        # row only when numbered; unnumbered wrapped words are usually table
        # column headers.
        if (prefix and not _ALLOWED_PREFIX.fullmatch(prefix)) or ("\n" in label_text.strip() and not prefix):
            position = match.start() + 1
            continue
        yield match
        position = max(match.end(), match.start() + 1)


# ── Eligibility facts written as prose or lists rather than label/value rows ──
# An amount must carry a currency marker or a crore/lakh unit.
_CURRENCY_AMOUNT = (
    r"(?:₹|\brs\b\.?|\binr\b)\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:crores?|cr\b\.?|lakhs?|lacs?))?"
    r"|(?<![\d.,])\d[\d,]*(?:\.\d+)?\s*(?:crores?|cr\b\.?|lakhs?|lacs?)"
)
_THRESHOLD = r"(?:not\s+less\s+than|minimum\s+(?:value\s+)?of|at\s+least|of\s+value|value\s+of)"
_PROSE_AMOUNT_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("Similar Work Value", re.compile(
        rf"\bsimilar\s+works?\b[^.;]{{0,250}}?{_THRESHOLD}\s*({_CURRENCY_AMOUNT})", re.I,
    )),
    ("Liquid Assets / Credit Facility", re.compile(
        r"\b(?:liquid\s+assets?|credit\s+facilit(?:y|ies)|working\s+capital)\b"
        rf"[^.;]{{0,120}}?{_THRESHOLD}\s*({_CURRENCY_AMOUNT})", re.I,
    )),
)
# "2AN-B", "2 A N - B", "2.5 AN – B".
_BID_CAPACITY_RE = re.compile(r"(?<![\w.])(\d(?:\.\d)?)\s*A\s*[x×*]?\s*N\s*[-–—]\s*B(?![\w-])")
_LIST_HEADINGS: tuple[tuple[str, re.Pattern], ...] = (
    ("Key Personnel", re.compile(
        r"^\s*(?:(?:\d{1,2}|[ivx]{1,5}|[a-z])[.)]\s*)?key\s+(?:technical\s+)?personnel\b", re.I,
    )),
    ("Key Equipment", re.compile(
        r"^\s*(?:(?:\d{1,2}|[ivx]{1,5}|[a-z])[.)]\s*)?(?:should\s+(?:possess|have)\s+(?:the\s+)?)?"
        r"key\s*(?:(?:/|&|and)\s*critical\s+)?(?:construction\s+)?(?:equipment|machinery)\b", re.I,
    )),
)
# "3. Tippers 5.5 Cum 20", "Project Manager     1", "Front End Loader 2 No’s".
_LIST_ITEM_RE = re.compile(
    r"^\s*(?:\(?(?:\d{1,2}|[ivx]{1,5})[.)]\s*)?([A-Za-z][^\n]{1,80}?)\s+(\d{1,3})\s*(?:nos?\.?|no[’']s|sets?)?\s*$",
    re.I,
)
MAX_LIST_ITEMS = 12


def _prose_amounts(body: str) -> list[tuple[str, str, str]]:
    found = []
    for field, pattern in _PROSE_AMOUNT_PATTERNS:
        for match in pattern.finditer(body):
            value = _clean(re.sub(r"\s+", " ", match.group(1)).rstrip("."))
            if _amount_rupees(value) in (None, 0):
                continue
            found.append((field, value, _clean(match.group(0))))
    return found


def _bid_capacity(body: str) -> list[tuple[str, str, str]]:
    found = []
    for match in _BID_CAPACITY_RE.finditer(body):
        line_start = body.rfind("\n", 0, match.start()) + 1
        line_end = body.find("\n", match.end())
        line = body[line_start:line_end if line_end >= 0 else len(body)]
        if not re.search(r"bid\s+capacity|capacity", line, re.I) and not re.search(
            r"bid\s+capacity", body[max(0, line_start - 300):line_start], re.I
        ):
            continue
        value = f"{match.group(1)}AN – B"
        # The definition that follows ("Where, A= ... N= ... B= ...").
        following = body[match.end():match.end() + 900]
        definitions = []
        for symbol in ("A", "N", "B"):
            definition = re.search(rf"(?m)^\s*{symbol}\s*=\s*([^\n]+)", following)
            if definition:
                definitions.append(f"{symbol} = {_clean(definition.group(1))[:70]}")
        excerpt = _clean(line)
        if definitions:
            excerpt = f"{excerpt} Where {'; '.join(definitions)}"[:240]
        found.append(("Bid Capacity Formula", value, excerpt))
    return found


def _numbered_lists(body: str) -> list[tuple[str, str, str]]:
    lines = body.split("\n")
    found = []
    for index, line in enumerate(lines):
        for field, heading in _LIST_HEADINGS:
            if not heading.match(line):
                continue
            items: list[str] = []
            skipped = 0
            for following in lines[index + 1:index + 60]:
                stripped = following.strip()
                item = _LIST_ITEM_RE.match(following)
                if item and re.search(r"[A-Za-z]{3}", item.group(1)):
                    name = re.sub(r"\s+", " ", item.group(1)).strip(" -–:")
                    items.append(f"{name}: {int(item.group(2))}")
                    continue
                if items:
                    break  # the list ended
                if not stripped:
                    continue
                skipped += 1  # column headers such as "S. No." or "Minimum Nos required"
                if skipped > 5:
                    break
            if len(items) < 2:
                continue
            shown = items[:MAX_LIST_ITEMS]
            value = "; ".join(shown)
            if len(items) > len(shown):
                value += f" (+{len(items) - len(shown)} more listed in the tender)"
            found.append((field, value, _clean(line)))
    return found


def _special_evidence(body: str) -> list[tuple[str, str, str]]:
    return _bid_capacity(body) + _prose_amounts(body) + _numbered_lists(body)


# ── Facts assembled across the whole document ─────────────────────────────
Section = tuple[str, str | None, str]
MAX_CONDITION_CHARS = 200
MAX_DOCUMENT_ITEMS = 20
MAX_DOCUMENT_ITEM_CHARS = 90
MAX_VALUE_CHARS = 700
MAX_DOCUMENTS_VALUE_CHARS = 1_400

_CONSORTIUM_RE = re.compile(r"\bconsorti(?:um|a)\b|\bjoint[\s-]+ventures?\b|\bJVs?\b", re.I)
_NUM = r"(?:\d{1,2}|one|two|three|four|five|six)"
_LEAD = r"\blead\s+(?:member|partner|bidder|firm)\b"
# (name, pattern, needs the sentence itself to mention the consortium/JV)
_CONSORTIUM_RULES: tuple[tuple[str, re.Pattern, bool], ...] = (
    ("allowed", re.compile(
        r"(?:consorti(?:um|a)|joint[\s-]+ventures?|\bJVs?\b)[^.;]{0,80}?\b(?:(?:is|are|shall\s+be|will\s+be|may\s+be)\s+)?"
        r"not\s+(?:be\s+)?(?:permitted|allowed|eligible|accepted|permissible)", re.I), True),
    ("members", re.compile(
        rf"(?:maximum|max\.?|up\s*to|upto|not\s+(?:more|exceed(?:ing)?)(?:\s+than)?|limited\s+to)\s+(?:of\s+)?{_NUM}\s*"
        r"(?:\(\s*\w+\s*\)\s*)?(?:members?|entities|partners?|firms?|companies)\b", re.I), False),
    ("lead share", re.compile(
        rf"{_LEAD}[^.;]{{0,160}}?\d{{1,3}}\s*%[^.;]{{0,120}}?\b(?:turnover|financial|net\s*worth|experience|qualif)", re.I), False),
    ("lead stake", re.compile(
        rf"(?:{_LEAD}|shall\s+hold)[^.;]{{0,160}}?\d{{1,3}}\s*%[^.;]{{0,60}}?\b(?:stake|participation|share(?:holding)?|equity|interest)", re.I), False),
    ("liability", re.compile(r"\bjoint(?:ly)?\s+(?:and|&)\s+several(?:ly)?\b", re.I), False),
    ("agreement", re.compile(
        r"(?:consortium|joint[\s-]+venture|\bJV\b)\s+(?:agreement|deed|mou\b)|memorandum\s+of\s+understanding", re.I), False),
)


_ABBREVIATION_END = re.compile(
    r"(?:\b(?:spl|no|nos|rs|dt|sl|dr|mr|ms|smt|sri|ltd|pvt|govt|dept|viz|etc|m/s))\.$", re.I,
)


def _sentences(body: str) -> list[str]:
    """Sentences of a page, not split after "Spl.", "No.", "Rs." or a list number."""
    # A list marker at the start of a line ("4. In case of ...") begins a new sentence.
    body = re.sub(r"(?m)^[ \t]*\(?(?:\d{1,2}|[a-z]|[ivx]{1,4})[.)][ \t]+(?=[A-Z])", "\u00a7 ", body)
    flat = re.sub(r"\s+", " ", body)
    flat = re.sub(r"\s*\bNOTE\s*:\s*", " \u00a7 ", flat)
    sentences: list[str] = []
    for part in re.split(r"(?<=[.;])\s+(?=[A-Z(])|\s*\u00a7\s*", flat):
        part = part.strip()
        if sentences and _ABBREVIATION_END.search(sentences[-1]):
            sentences[-1] = f"{sentences[-1]} {part}"
        elif part:
            sentences.append(part)
    return sentences


def _shorten(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip(" ;.,:-–")
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-–(") + "…"


def _consortium_conditions(sections: list[Section]) -> list[Evidence]:
    """The consortium/JV rules: members, the lead's share and stake, liability, the agreement.

    Each rule is recorded once, from the first sentence that states it on a
    page that speaks of a consortium or joint venture.
    """
    kept: dict[str, str] = {}
    first: tuple[str, str | None] | None = None
    for source, page, body in sections:
        if not _CONSORTIUM_RE.search(body):
            continue
        for sentence in _sentences(body):
            if len(sentence) < 25 or len(sentence) > 600:
                continue
            in_sentence = bool(_CONSORTIUM_RE.search(sentence)) or bool(re.search(_LEAD, sentence, re.I))
            for name, pattern, needs_mention in _CONSORTIUM_RULES:
                if name in kept or not pattern.search(sentence):
                    continue
                if needs_mention and not in_sentence:
                    continue
                if any(sentence == other for other in kept.values()):
                    kept[name] = ""  # the sentence already recorded states this rule too
                    continue
                kept[name] = sentence
                first = first or (source, page)
    conditions = [_shorten(text, MAX_CONDITION_CHARS) for text in kept.values() if text]
    if not conditions or first is None:
        return []
    value = ""
    for condition in conditions:
        joined = f"{value}; {condition}" if value else condition
        if len(joined) > MAX_VALUE_CHARS:
            break
        value = joined
    if not value:
        return []
    return [Evidence("Consortium / JV Conditions", value, first[0], first[1], conditions[0][:240])]


_MARKS_TOTAL_RES = (
    re.compile(r"\bout\s+of\s+(?:a\s+)?(?:total\s+(?:of\s+)?)?(\d{2,4})\s*marks\b", re.I),
    re.compile(r"\bevaluation\s+criteri[ao]n?\b[^\n\d]{0,20}(\d{2,4})\s*marks\b", re.I),
    re.compile(r"\btotal\s+(?:of\s+)?(\d{2,4})\s*marks\b", re.I),
)
_MARKS_MINIMUM_RES = (
    re.compile(
        r"\b(?:less\s+than|minimum(?:\s+of)?|at\s*least|not\s+less\s+than)\s+(\d{1,3})\s*(?:\(\s*[a-z\s-]+\)\s*)?"
        r"(?:%\s*)?(?:(?:qualifying|technical)\s+)?marks\b", re.I),
    re.compile(r"\bqualifying\s+marks?\s*(?:is|are|shall\s+be|will\s+be|of|[:=\-–])\s*(\d{1,3})\b(?!\.\d)", re.I),
)
_MARKS_TOTAL_LINE = re.compile(r"^\s*(?:grand\s+)?total(?:\s+marks)?\s*:?\s*(\d{2,4})\s*$", re.I)
# "Credentials 60", "Technical Presentation: Approach & Planning 40".
_MARKS_GROUP_LINE = re.compile(r"^\s*([A-Z][^\d\n]{4,100}?)\s*[:\-–]?\s+(\d{1,3})\s*$")
_MARKS_ROW_START = re.compile(r"^\s*([A-Z])(?:\s*$|\s+(?=[A-Z][a-z]))")
MAX_MARK_TITLE_CHARS = 42


def _marks_breakdown(lines: list[str], total: int) -> list[str]:
    """Breakdown lines of the marks table that ends in "Total <total>".

    The headings ("Credentials 60") are kept when they add up to the total,
    and so are the lettered criteria (A, B, C ...); anything that does not add
    up is left out rather than guessed.
    """
    end = next((i for i, line in enumerate(lines)
                if (m := _MARKS_TOTAL_LINE.match(line)) and int(m.group(1)) == total), None)
    if end is None:
        return []
    start = max(0, end - 220)
    for index in range(end - 1, start - 1, -1):
        if re.search(r"evaluation\s+criteri|max(?:imum|\.)?\s*marks|marking\s+scheme|scoring", lines[index], re.I):
            start = index
    groups: list[tuple[str, int]] = []
    rows: list[tuple[str, list[str]]] = []
    expected = "A"
    for line in lines[start:end]:
        if PAGE_RE.match(line.strip()):
            continue
        group = _MARKS_GROUP_LINE.match(line)
        row = _MARKS_ROW_START.match(line)
        if row and row.group(1) == expected:
            rows.append((expected, [line.strip()[1:].strip()]))
            expected = chr(ord(expected) + 1)
        elif group and int(group.group(2)) <= total and not (rows and line.strip()[0].islower()):
            groups.append((_shorten(group.group(1), 80), int(group.group(2))))
            if rows:
                rows.append(("", []))  # a heading ends the row above it
        elif rows:
            rows[-1][1].append(line.strip())
    out: list[str] = []
    if len(groups) >= 2 and sum(marks for _, marks in groups) == total:
        out.extend(f"{name}: {marks}" for name, marks in groups)
    criteria: list[str] = []
    scored = 0
    for letter, parts in rows:
        if not letter:
            continue
        text = re.sub(r"\s+", " ", " ".join(part for part in parts if part))
        marks = re.search(r"(?:^|\s)(\d{1,3})\s*$", text)
        if not marks or not re.search(r"[A-Za-z]{3}", text):
            return out
        scored += int(marks.group(1))
        criteria.append(f"{letter}. {_shorten(text, MAX_MARK_TITLE_CHARS)}: {int(marks.group(1))}")
    if len(criteria) >= 2 and scored == total:
        out.extend(criteria)
    return out


def _evaluation_marks(sections: list[Section]) -> list[Evidence]:
    """Total marks, the minimum qualifying marks and, where it adds up, the breakdown."""
    totals: list[int] = []
    minimums: list[int] = []
    first: tuple[str, str | None, str] | None = None
    for source, page, body in sections:
        # Table-of-contents lines ("4. EVALUATION — 100 MARKS ..... 16") are not the criteria.
        flat = " ".join(line.strip() for line in body.split("\n") if not re.search(r"\.{5,}", line))
        for pattern in _MARKS_TOTAL_RES:
            for match in pattern.finditer(flat):
                totals.append(int(match.group(1)))
                first = first or (source, page, _clean(flat[max(0, match.start() - 80):match.end() + 60]))
        for pattern in _MARKS_MINIMUM_RES:
            for match in pattern.finditer(flat):
                minimums.append(int(match.group(1)))
                first = first or (source, page, _clean(flat[max(0, match.start() - 80):match.end() + 60]))
    if first is None:
        return []
    total = max(set(totals), key=totals.count) if totals else None
    minimums = [value for value in dict.fromkeys(minimums) if total is None or value < total]
    if total is None and not minimums:
        return []
    parts: list[str] = []
    if total is not None:
        parts.append(f"Total {total} marks")
    if len(minimums) == 1:
        parts.append(f"minimum qualifying {minimums[0]} marks")
    elif minimums:
        parts.append("minimum qualifying marks stated differently: " + " / ".join(map(str, minimums)))
    if total is not None:
        by_source: dict[str, list[str]] = {}
        for source, page, body in sections:
            by_source.setdefault(source, []).extend(body.split("\n"))
        for lines in by_source.values():
            breakdown = _marks_breakdown(lines, total)
            if breakdown:
                while breakdown and len("; ".join(parts + breakdown)) > MAX_VALUE_CHARS:
                    breakdown.pop()
                parts.extend(breakdown)
                break
    return [Evidence("Technical Evaluation Marks", "; ".join(parts), first[0], first[1], first[2])]


_DOCUMENT_HEADING_RE = re.compile(
    r"documents?\s+(?:required|to\s+be\s+(?:submitted|uploaded|furnished|enclosed|attached))"
    r"|(?:scan\s+and\s+)?upload\s+the\s+(?:below|following)(?:\s+mentioned)?\s+documents?"
    r"|list\s+of\s+(?:mandatory\s+)?documents|check\s*-?\s*list\s+of\s+documents|mandatory\s+documents",
    re.I,
)
_REQUIRED_CELL = re.compile(r"\s*\b(?:mandatory|compulsory)\s*$", re.I)
_NUMBERED_ITEM = re.compile(r"^\s*\(?(\d{1,2})[.)]\s+(\S.*)$")
_LIST_END = re.compile(r"^\s*(?:note\b|n\.b\.|place\s*:|date\s*:|signature|seal\b)", re.I)


def _document_item(text: str) -> str | None:
    text = re.sub(r"^\s*document\s+name\s+required\b", "", text, flags=re.I)
    text = _shorten(re.sub(r"\s*/-\s*$", "", text.strip()), MAX_DOCUMENT_ITEM_CHARS)
    if len(text) < 4 or not re.search(r"[A-Za-z]{3}", text):
        return None
    if re.fullmatch(r"(?:document\s+name|required|sl\.?\s*no\.?|description|particulars|yes\s*/\s*no)[\s\w./]*", text, re.I):
        return None
    return text


def _documents_after(lines: list[str]) -> list[str]:
    """The explicit list under a documents heading: a "Mandatory" column or numbered items."""
    window = lines[:90]
    if sum(1 for line in window if _REQUIRED_CELL.search(line)) >= 3:
        items, current = [], []
        for line in window:
            if _LIST_END.match(line):
                break
            cell = _REQUIRED_CELL.search(line)
            current.append(line[:cell.start()] if cell else line)
            if cell:
                item = _document_item(" ".join(current))
                if item:
                    items.append(item)
                current = []
        return items
    items = []
    current = ""
    waited = 0
    number = 0
    for line in window:
        numbered = _NUMBERED_ITEM.match(line)
        if numbered and int(numbered.group(1)) == number + 1:
            if current:
                items.append(current)
            number += 1
            current = numbered.group(2)
        elif not number:
            waited += bool(line.strip())
            if waited > 6:
                break
        elif not line.strip() or _LIST_END.match(line) or numbered:
            break
        else:
            current = f"{current} {line.strip()}"
    if current:
        items.append(current)
    cleaned = [item for item in map(_document_item, items) if item]
    return cleaned if len(cleaned) >= 3 and len(cleaned) == len(items) else []


def _mandatory_documents(sections: list[Section]) -> list[Evidence]:
    """Every explicit document checklist in the tender, merged into one list."""
    items: list[str] = []
    seen: set[str] = set()
    first: tuple[str, str | None, str] | None = None
    for source, page, body in sections:
        for heading in _DOCUMENT_HEADING_RE.finditer(body):
            line_start = body.rfind("\n", 0, heading.start()) + 1
            line_end = body.find("\n", heading.end())
            if line_end < 0:
                continue
            listed = _documents_after(body[line_end + 1:].split("\n"))
            if not listed:
                continue
            first = first or (source, page, _clean(body[line_start:line_end]))
            for item in listed:
                key = re.sub(r"\W+", "", item).casefold()
                if key not in seen:
                    seen.add(key)
                    items.append(item)
    if first is None or len(items) < 3:
        return []
    shown = items[:MAX_DOCUMENT_ITEMS]
    while len(shown) > 3 and len("; ".join(shown)) > MAX_DOCUMENTS_VALUE_CHARS:
        shown.pop()
    value = "; ".join(shown)
    if len(items) > len(shown):
        value += f" (+{len(items) - len(shown)} more listed in the tender)"
    return [Evidence("Mandatory Documents", value, first[0], first[1], first[2])]


_HARD_COPY_RE = re.compile(
    r"\bhard\s+cop(?:y|ies)\b|\battested\s+copies\b|\boriginal\s+(?:e\.?m\.?d|d\.?d|demand\s+draft|documents?|certificates?)\b",
    re.I,
)
_HARD_COPY_WHEN_RE = re.compile(
    r"\b(?:on\s+or\s+before|before|prior\s+to|within\s+\d+|not\s+later\s+than|by\s+\d)", re.I,
)
MAX_HARD_COPY_CHARS = 320


def _hard_copy_submission(sections: list[Section]) -> list[Evidence]:
    """The first sentence saying which physical documents must reach the authority, and by when."""
    fallback: Evidence | None = None
    for source, page, body in sections:
        for sentence in _sentences(body):
            if not (40 <= len(sentence) <= 700 and _HARD_COPY_RE.search(sentence) and _HARD_COPY_WHEN_RE.search(sentence)
                    and re.search(r"\b(?:submit|produce|furnish|deliver|reach|send)", sentence, re.I)):
                continue
            value = _shorten(sentence, MAX_HARD_COPY_CHARS)
            found = Evidence("Hard Copy Submission", value, source, page, value[:240])
            # A deadline tied to the bid opening matters more than one after the award.
            if re.search(r"\bopening\b|\bbid\s+submission\b|\bclosing\b", sentence, re.I) and not re.search(
                r"\bsuccessful\b|\bapproved\s+tenderer\b|\bL-?1\b|\bagreement\b", sentence, re.I
            ):
                return [found]
            fallback = fallback or found
    return [fallback] if fallback else []


def _document_evidence(sections: list[Section]) -> list[Evidence]:
    return (
        _consortium_conditions(sections) + _evaluation_marks(sections)
        + _mandatory_documents(sections) + _hard_copy_submission(sections)
    )


def extract_tender_evidence(text: str, max_per_field: int = 3) -> list[Evidence]:
    """Scan all source/page sections and return cited, validated metadata candidates.

    A label's value is taken from its own line (after ``:``, ``-``, ``|`` or a
    tab) or, for NIT tables whose value cell wraps, from the following lines.
    Every value must look like its field (a date for deadlines, an amount for
    EMD/contract value, a number of days/months for durations), so sentence
    fragments that merely follow a label are never recorded as facts.
    """
    source = "Pasted tender text"
    page: str | None = None
    sections: list[tuple[str, str | None, str]] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            sections.append((source, page, "\n".join(buffer)))
            buffer.clear()

    for raw_line in text.replace("\r\n", "\n").split("\n"):
        source_match = SOURCE_RE.match(raw_line.strip())
        page_match = PAGE_RE.match(raw_line.strip())
        if source_match:
            flush()
            source = source_match.group(1).strip()
            page = None
        elif page_match:
            flush()
            page = page_match.group(1)
        else:
            buffer.append(raw_line)
    flush()

    found: list[Evidence] = []
    seen: set[tuple[str, object]] = set()
    counts: dict[str, int] = {}
    sections = [(s, p, _dehyphenate(body)) for s, p, body in sections]
    for section_source, section_page, body in sections:
        lines = body.split("\n")
        line_starts: list[int] = []
        offset = 0
        for line in lines:
            line_starts.append(offset)
            offset += len(line) + 1
        for field, patterns in FIELD_PATTERNS:
            if counts.get(field, 0) >= max_per_field:
                continue
            for pattern in patterns:
                for match in _label_matches(pattern, body):
                    line_start = body.rfind("\n", 0, match.start()) + 1
                    value_line_index = body.count("\n", 0, match.start(1))
                    inline = _cell(match.group(1))
                    value = validate_value(field, inline, body[line_start:match.start(1)])
                    value_line = ""
                    if value is None and field in TEXT_FIELDS and len(inline) <= 120:
                        value, value_line = _value_after_label(field, lines, value_line_index, inline)
                    elif value is None and len(inline) <= 30:
                        value, value_line = _value_after_label(field, lines, value_line_index, inline)
                    if not value:
                        continue
                    key = (field, _fact_key(field, value))
                    if key in seen:
                        continue
                    seen.add(key)
                    line_end = body.find("\n", match.end(1))
                    if line_end < 0:
                        line_end = len(body)
                    excerpt = _clean(body[line_start:line_end])
                    if value_line:
                        excerpt = f"{excerpt} … {_clean(value_line)}"[:240]
                    found.append(Evidence(field, value, section_source, section_page, excerpt))
                    counts[field] = counts.get(field, 0) + 1
                    if counts[field] >= max_per_field:
                        break
                if counts.get(field, 0) >= max_per_field:
                    break
        for field, value, excerpt in _special_evidence(body):
            if counts.get(field, 0) >= max_per_field:
                continue
            key = (field, _fact_key(field, value))
            if key in seen:
                continue
            seen.add(key)
            found.append(Evidence(field, value, section_source, section_page, excerpt))
            counts[field] = counts.get(field, 0) + 1
    found.extend(_document_evidence(sections))
    return _drop_fees_read_as_value(found)


def _drop_fees_read_as_value(found: list[Evidence]) -> list[Evidence]:
    """A "contract value" equal to the tender's own fee or EMD is that fee, not a value."""
    not_values = {
        _amount_rupees(item.value) for item in found if item.field in {"Application / Tender Fee", "EMD Amount"}
    } - {None}
    return [
        item for item in found
        if not (item.field == "Estimated Contract Value" and _amount_rupees(item.value) in not_values)
    ]


def _parse_date(value: str) -> str | None:
    match = DATE_RE.search(value)
    if not match:
        return None
    raw = match.group(0)
    numeric = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2}|\d{4})", raw)
    if numeric:
        day, month, year = (int(part) for part in numeric.groups())
    else:
        month_name = re.search(_MONTH, raw, re.I)
        day_match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b(?!\d)", raw.replace(month_name.group(0), " "))
        year_match = re.search(r"\d{4}", raw)
        if not (month_name and day_match and year_match):
            return None
        month = _MONTHS.index(month_name.group(0)[:3].casefold()) + 1
        day, year = int(day_match.group(1)), int(year_match.group(0))
    if year < 100:
        year += 2000
    return f"{year:04d}-{month:02d}-{day:02d}"


def _parse_time(value: str) -> str | None:
    date = DATE_RE.search(value)
    rest = value[date.end():] + " " + value[:date.start()] if date else value
    match = TIME_RE.search(rest)
    if not match:
        return None
    parts = re.match(r"(\d{1,2})(?:[.:](\d{2}))?\s*([ap])?", match.group(0), re.I)
    hour, minute = int(parts.group(1)), int(parts.group(2) or 0)
    meridiem = (parts.group(3) or "").casefold()
    if meridiem == "p" and hour < 12:
        hour += 12
    elif meridiem == "a" and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute:02d}"


def _amount_rupees(value: str) -> int | None:
    match = re.search(r"\d[\d,]*(?:\.\d+)?", value)
    if not match:
        return None
    number = float(match.group(0).replace(",", ""))
    unit = value[match.end():].casefold()
    if re.match(r"\s*(?:crores?|cr\b)", unit):
        number *= 10_000_000
    elif re.match(r"\s*(?:lakhs?|lacs?)", unit):
        number *= 100_000
    return round(number)


def _fact_key(field: str, value: str) -> object:
    """A normalised form so the same fact written two ways is not a conflict."""
    if field in DATE_FIELDS:
        date = _parse_date(value)
        if date:
            return (date, _parse_time(value))
    if field in AMOUNT_FIELDS:
        rupees = _amount_rupees(value)
        if rupees is not None:
            return rupees
    if field in LIST_FIELDS:
        # The shown items identify the list; a longer copy of it is the same fact.
        return tuple(re.sub(r"\W+", "", item).casefold() for item in value.split(" (+")[0].split("; "))
    if field in DURATION_FIELDS:
        match = re.search(r"(\d+(?:\.\d+)?)\s*\)?\s*(?:\(\s*[a-z\s-]+\)\s*)?(?:calendar\s+|working\s+)?(day|week|month|year)", value, re.I)
        if match:
            return (float(match.group(1)), match.group(2).casefold())
    return re.sub(r"\W+", "", value).casefold()


def _consistent(field: str, items: list[Evidence]) -> Evidence | None:
    """The one candidate all others agree with, or None when they conflict."""
    keys = [_fact_key(field, item.value) for item in items]
    if len(set(keys)) == 1:
        return items[0]
    if field in DATE_FIELDS and all(isinstance(key, tuple) for key in keys):
        # "30.09.2026" and "30.09.2026 @ 3.00 PM" agree; keep the precise one.
        dates = {key[0] for key in keys}
        times = {key[1] for key in keys if key[1]}
        if len(dates) == 1 and len(times) <= 1:
            return next((item for item, key in zip(items, keys) if key[1]), items[0])
    return None


def format_evidence_block(evidence: list[Evidence]) -> str:
    """Format an authoritative, compact block for the beginning of the prompt."""
    if not evidence:
        return ""
    lines = [
        "=== DETERMINISTIC METADATA EVIDENCE ===",
        "Use the candidates below instead of writing 'Not Specified' when the cited excerpt supports the value.",
        "Do not combine conflicting candidates; flag conflicts for human review. Never replace a candidate with a guess.",
    ]
    for item in evidence:
        location = item.source + (f", page {item.page}" if item.page else "")
        value = item.value
        if item.field in DATE_FIELDS:
            date, time = _parse_date(value), _parse_time(value)
            if date and time:
                value = f"{value} (= {date} {time})"
        lines.append(f"- {item.field}: {value} [Source: {location}] [Excerpt: {item.excerpt}]")
    lines.append("=== END DETERMINISTIC METADATA EVIDENCE ===")
    return "\n".join(lines)


def canonical_fact_record(evidence: list[Evidence]) -> tuple[dict[str, Evidence], dict[str, list[Evidence]]]:
    """Return unambiguous facts and fields whose extracted values conflict.

    This record is deliberately conservative: a field becomes canonical only
    when every extracted candidate normalises to the same value. Conflicting
    candidates are never silently resolved by picking the first match.
    """
    grouped: dict[str, list[Evidence]] = {}
    for item in evidence:
        grouped.setdefault(item.field, []).append(item)

    facts: dict[str, Evidence] = {}
    conflicts: dict[str, list[Evidence]] = {}
    for field, items in grouped.items():
        agreed = _consistent(field, items)
        if agreed is not None:
            facts[field] = agreed
        else:
            conflicts[field] = items
    return facts, conflicts


def serialize_canonical_facts(evidence: list[Evidence]) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    """Create JSON-safe canonical facts for durable analysis-job context."""
    facts, conflicts = canonical_fact_record(evidence)

    def as_dict(item: Evidence) -> dict:
        return {
            "field": item.field,
            "value": item.value,
            "source": item.source,
            "page": item.page,
            "excerpt": item.excerpt,
        }

    return (
        {field: as_dict(item) for field, item in facts.items()},
        {field: [as_dict(item) for item in items] for field, items in conflicts.items()},
    )


def prefer_newest_evidence(layers: list[list[Evidence]]) -> list[Evidence]:
    """Merge evidence from newest to oldest document layers.

    For each field, only the newest layer that mentions it is kept, so a
    corrigendum's deadline replaces the original's instead of being reported
    as a conflict. Conflicts *within* one layer are still preserved.
    """
    merged: list[Evidence] = []
    claimed: set[str] = set()
    for layer in layers:
        fields_here = {item.field for item in layer}
        merged.extend(item for item in layer if item.field not in claimed)
        claimed |= fields_here
    return merged
