"""Deterministic safety gate for generated tender-analysis reports.

Language models remain useful for synthesis, but a tender report must not be
released solely because generation finished. These checks catch the failure
modes that can be verified without another model call: canonical-fact
contradictions, unfinished template placeholders, unsupported requirements,
unsafe quote claims and missing/multiple final decisions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class QualityIssue:
    code: str
    severity: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


_PLACEHOLDER_PATTERNS = (
    r"\[(?:department|insert|confirm before submission|company|name|date|amount)[^\]]*\]",
    r"\[(?:x|xx|xxx)\]\s*/\s*100",
    r"\b(?:TBD|TO BE FILLED|PLACEHOLDER)\b",
)

_UNSUPPORTED_CONTRACT_VALUE_PATTERN = re.compile(
    r"\b(?:estimated|project|tender|contract)(?:\s+project)?\s+value"
    r"\s*(?:is|of|at|:)?\s*(?:₹|INR|Rs\.?)\s*[\d,]+(?:\.\d+)?(?:\s*(?:crore|lakh|lakhs?))?",
    re.I,
)

_UNSUPPORTED_REQUIREMENTS: tuple[tuple[str, str], ...] = (
    ("ISO certification", r"\bISO(?:\s*\d{4,5}(?::\d{4})?)?\b"),
    ("OEM authorisation", r"\bOEM\s+authori[sz]ation"),
    ("digital signature certificate", r"\b(?:DSC|digital signature certificate)\b"),
    ("PF/ESI", r"\b(?:PF|EPF|ESI)\b"),
    ("encryption", r"\bencrypt(?:ion|ed)?\b"),
    ("file-size limit", r"\bfile\s*size\s*(?:limit|maximum|max)\b"),
    ("portal upload sequence", r"\bupload\s+sequence\b"),
    ("file naming or format rule", r"\b(?:file\s+(?:naming|format|type)|page\s+limit|headers?)\b"),
    ("mandatory CV requirement", r"\bCVs?\b"),
    ("technical brochure requirement", r"\btechnical\s+brochures?\b"),
)

_SAFE_REQUIREMENT_CONTEXT = re.compile(
    r"(?:"
    r"not\s+(?:specified|required|verified|stated|mentioned|supported|found|present)|"
    r"no\s+(?:tender\s+|documentary\s+|supplied\s+)?evidence|"
    r"(?:absent|missing)\s+from\s+(?:the\s+)?(?:supplied\s+)?tender|"
    r"tender\s+(?:is\s+)?silent|unsupported\s+by\s+(?:the\s+)?tender|"
    r"do\s+not\s+(?:treat|assume|add|require|claim)|"
    r"(?:cannot|could\s+not)\s+(?:verify|confirm|establish)|"
    r"(?:verify|confirm|clarify|check)\s+whether|"
    r"(?:if|where|only\s+if)\s+(?:it\s+is\s+)?required"
    r")",
    re.I,
)

_ASSERTED_REQUIREMENT_CONTEXT = re.compile(
    r"\b(?:mandatory|required|must|shall|pending|expired|missing|gap|blocker|"
    r"non[- ]?compliant|obtain|submit|upload|include|provide|renew|ensure|"
    r"encrypt|follow|comply|available|held|valid)\b",
    re.I,
)


def _containing_claim(text: str, start: int, end: int) -> str:
    """Return only the bullet/sentence containing a matched requirement.

    A wide character window can accidentally combine a safe statement such as
    "DSC is not specified" with an unrelated mandatory action on the next
    bullet. Keeping the context to one claim prevents that false positive.
    """
    left = max(text.rfind("\n", 0, start), text.rfind(".", 0, start)) + 1
    newline = text.find("\n", end)
    period = text.find(".", end)
    candidates = [position for position in (newline, period) if position >= 0]
    right = min(candidates) + 1 if candidates else len(text)
    return text[left:right].strip()


def remove_unsupported_requirement_claims(final: str, tender_text: str) -> str:
    """Remove affirmative requirement lines that have no tender evidence.

    This is intentionally conservative: it removes a whole line instead of
    trying to rewrite factual content. Safe uncertainty statements and terms
    that occur in the tender are retained.
    """
    cleaned: list[str] = []
    for line in final.splitlines():
        remove = False
        for _, pattern in _UNSUPPORTED_REQUIREMENTS:
            if re.search(pattern, tender_text, re.I):
                continue
            matches = list(re.finditer(pattern, line, re.I))
            if not matches:
                continue
            if any(
                not _SAFE_REQUIREMENT_CONTEXT.search(
                    _containing_claim(line, match.start(), match.end())
                )
                and _ASSERTED_REQUIREMENT_CONTEXT.search(
                    _containing_claim(line, match.start(), match.end())
                )
                for match in matches
            ):
                remove = True
                break
        if not remove:
            cleaned.append(line)
    return "\n".join(cleaned).strip()


def remove_unfinished_placeholder_lines(final: str) -> str:
    """Drop incomplete template lines instead of guessing their values."""
    return "\n".join(
        line
        for line in final.splitlines()
        if not any(re.search(pattern, line, re.I) for pattern in _PLACEHOLDER_PATTERNS)
    ).strip()


_VALUED_AT_PATTERN = re.compile(
    r"\b(?:project|tender|contract)\s+(?:is\s+)?valued\s+at\s+(?:₹|INR|Rs\.?)\s*[\d,]+(?:\.\d+)?"
    r"(?:\s*(?:crore|lakh|lakhs?))?",
    re.I,
)


def remove_unsupported_contract_value(final: str, canonical_facts: dict | None) -> str:
    """Replace a contract value the tender never states with an explicit gap.

    The model sometimes invents an estimated value; rather than blocking the
    whole report, the invented figure is removed deterministically.
    """
    if canonical_facts and "Estimated Contract Value" in canonical_facts:
        return final
    final = _UNSUPPORTED_CONTRACT_VALUE_PATTERN.sub("Estimated contract value: Not stated in the tender", final)
    return _VALUED_AT_PATTERN.sub("Contract value: Not stated in the tender", final)


def sanitize_final_report(
    final: str,
    tender_text: str,
    canonical_facts: dict | None = None,
    bid_manager_report: str | None = None,
) -> str:
    """Apply deterministic, non-generative cleanup before final QA."""
    cleaned = remove_unfinished_placeholder_lines(
        remove_unsupported_contract_value(
            remove_unsupported_requirement_claims(final, tender_text), canonical_facts,
        )
    )
    return insert_inferred_decision(cleaned, bid_manager_report)


def _normalise_decision(raw: str) -> str:
    raw = re.sub(r"\s+", " ", raw.upper()).strip()
    if raw.startswith("CONDITIONAL"):
        return "CONDITIONAL GO"
    if raw in {"NO GO", "NO-GO", "NO BID", "NO-BID", "NOGO", "NOBID"}:
        return "NO-GO"
    return "GO"


# The "GO / NO-GO" label names both options; it is not itself a decision.
_DECISION_LABEL = re.compile(r"\bGO\s*/\s*NO[- ]?GO\b")
# Case-sensitive: only upper-case decision words count, so prose such as
# "go ahead" or "the bid" is never read as a verdict.
_BARE_DECISION = re.compile(r"(?<![\w-])(CONDITIONAL\s+(?:GO|BID)|NO[- ]GO|NO[- ]BID|GO|BID)(?![\w-])")
_CAPS_WORD = re.compile(r"[A-Z][A-Z&]+")


def _bare_decision_values(text: str) -> list[str]:
    """Decision words written outside an explicit decision line.

    A bare GO/BID that is part of an all-caps phrase ("BID READINESS",
    "TECHNICAL BID") is a heading, not a verdict, and is ignored.
    """
    text = _DECISION_LABEL.sub(" ", text)
    values: list[str] = []
    for match in _BARE_DECISION.finditer(text):
        word = match.group(1)
        if word in {"GO", "BID"}:
            before = text[:match.start()].rstrip(" \t*")
            after = text[match.end():].lstrip(" \t*")
            previous = re.search(r"([A-Za-z&]+)$", before)
            following = re.match(r"[A-Za-z&]+", after)
            if (previous and _CAPS_WORD.fullmatch(previous.group(1))) or (
                following and _CAPS_WORD.fullmatch(following.group(0))
            ):
                continue
        value = _normalise_decision(word)
        if value not in values:
            values.append(value)
    return values


def _unambiguous_decision(text: str) -> str | None:
    explicit = _decision_values(text)
    if explicit:
        return explicit[0] if len(explicit) == 1 else None
    bare = _bare_decision_values(text)
    return bare[0] if len(bare) == 1 else None


def insert_inferred_decision(final: str, bid_manager_report: str | None = None) -> str:
    """Add an explicit decision line when the model stated its verdict elsewhere.

    The decision is taken from the final report's own text or, failing that,
    from the Bid Manager's recommendation, and only when exactly one distinct
    decision appears there. Otherwise the report is returned unchanged so the
    quality gate still blocks it.
    """
    if not final.strip() or _decision_values(final):
        return final
    decision, source = _unambiguous_decision(final), "the final report text"
    if decision is None and not _bare_decision_values(final) and bid_manager_report:
        decision, source = _unambiguous_decision(bid_manager_report), "the Bid Manager recommendation"
    if decision is None:
        return final
    line = f"GO / NO-GO DECISION: {decision} (inferred from {source})"
    lines = final.split("\n")
    # Keep a leading markdown title first; the decision goes right after it.
    index = next((i for i, value in enumerate(lines) if value.strip()), 0)
    if lines and lines[index].lstrip().startswith("#"):
        return "\n".join(lines[:index + 1] + ["", line] + lines[index + 1:])
    return "\n".join(lines[:index] + [line, ""] + lines[index:])


def _decision_values(text: str) -> list[str]:
    values: list[str] = []
    pattern = re.compile(
        r"(?:GO\s*/\s*NO-GO\s+DECISION|FINAL\s+(?:VERDICT|DECISION)|RECOMMENDATION)\s*\**\s*:\s*"
        r"(?:\*{0,2})\s*(CONDITIONAL\s+(?:GO|BID)|NO[- ]?GO|NO[- ]?BID|GO|BID)",
        re.I,
    )
    for match in pattern.finditer(text):
        raw = re.sub(r"\s+", " ", match.group(1).upper()).strip()
        if raw.startswith("CONDITIONAL"):
            value = "CONDITIONAL GO"
        elif raw in {"NO GO", "NO-GO", "NO BID", "NO-BID"}:
            value = "NO-GO"
        else:
            value = "GO"
        if value not in values:
            values.append(value)
    return values


def _line_claims_not_specified(text: str, field_terms: tuple[str, ...]) -> bool:
    for line in text.splitlines():
        lowered = line.casefold()
        if any(term.casefold() in lowered for term in field_terms) and re.search(
            r"\b(?:not specified|not provided|unknown|not available)\b", line, re.I
        ):
            return True
    return False


def _money_numbers(value: str) -> set[str]:
    return {
        re.sub(r"\D", "", match)
        for match in re.findall(r"\d[\d,]*(?:\.\d+)?", value)
        if re.sub(r"\D", "", match)
    }


def audit_final_report(
    final: str,
    tender_text: str,
    canonical_facts: dict[str, dict] | None = None,
) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    canonical_facts = canonical_facts or {}

    for pattern in _PLACEHOLDER_PATTERNS:
        if re.search(pattern, final, re.I):
            issues.append(QualityIssue(
                "unfinished_placeholder", "critical",
                "The final report contains an unfinished template placeholder.",
            ))
            break

    decisions = _decision_values(final)
    if not decisions:
        issues.append(QualityIssue(
            "missing_final_decision", "critical",
            "The final report does not contain one explicit GO, NO-GO, or CONDITIONAL GO decision.",
        ))
    elif len(decisions) > 1:
        issues.append(QualityIssue(
            "conflicting_final_decisions", "critical",
            f"The final report contains conflicting decisions: {', '.join(decisions)}.",
        ))

    if (
        "Estimated Contract Value" not in canonical_facts
        and (
            _UNSUPPORTED_CONTRACT_VALUE_PATTERN.search(final)
            or re.search(
                r"\b(?:project|tender|contract)\s+(?:is\s+)?valued\s+at\s+(?:₹|INR|Rs\.?)\s*[\d,]+",
                final,
                re.I,
            )
        )
    ):
        issues.append(QualityIssue(
            "unsupported_contract_value", "critical",
            "The report states a contract value even though no canonical contract-value evidence was extracted.",
        ))

    if decisions == ["NO-GO"]:
        conditions = re.search(
            r"CONDITIONS\s*\(if Conditional Go\)\s*(?P<body>.*?)(?:KEY STRENGTHS|CRITICAL RISKS|$)",
            final,
            re.I | re.S,
        )
        if conditions and not re.search(r"\b(?:none|not applicable|n/?a)\b", conditions.group("body"), re.I):
            issues.append(QualityIssue(
                "no_go_with_conditions", "critical",
                "The report gives conditional-GO conditions despite issuing a final NO-GO decision.",
            ))

    field_terms = {
        "Tender Title": ("tender title",),
        "Estimated Contract Value": ("estimated contract value", "project value", "tender value"),
        "EMD Amount": ("emd amount", "earnest money", "bid security"),
        "Bid Submission Deadline": ("bid submission deadline", "submission deadline"),
        "Bid Opening Date": ("bid opening date",),
    }
    for field, terms in field_terms.items():
        fact = canonical_facts.get(field)
        if fact and _line_claims_not_specified(final, terms):
            issues.append(QualityIssue(
                "canonical_fact_omitted", "critical",
                f"{field} is reported as unavailable although cited tender evidence provides: {fact.get('value')}.",
            ))
        if fact and field in {"Estimated Contract Value", "EMD Amount"}:
            canonical_amounts = _money_numbers(str(fact.get("value", "")))
            if canonical_amounts:
                for line in final.splitlines():
                    lowered = line.casefold()
                    if not any(term.casefold() in lowered for term in terms):
                        continue
                    reported = _money_numbers(line)
                    if reported and canonical_amounts.isdisjoint(reported):
                        issues.append(QualityIssue(
                            "canonical_amount_conflict", "critical",
                            f"{field} conflicts with the cited canonical value {fact.get('value')}.",
                        ))
                        break

    tender_lower = tender_text.casefold()
    for label, pattern in _UNSUPPORTED_REQUIREMENTS:
        if not re.search(pattern, final, re.I) or re.search(pattern, tender_text, re.I):
            continue
        # Mere mention is not a requirement. Flag only an affirmative tender
        # obligation/status, while allowing explicit uncertainty or absence.
        unsafe = False
        for match in re.finditer(pattern, final, re.I):
            context = _containing_claim(final, match.start(), match.end())
            if _SAFE_REQUIREMENT_CONTEXT.search(context):
                continue
            if _ASSERTED_REQUIREMENT_CONTEXT.search(context):
                unsafe = True
                break
        if unsafe and label.casefold() not in tender_lower:
            issues.append(QualityIssue(
                "unsupported_requirement", "critical",
                f"The report introduces {label} without support in the supplied tender evidence.",
            ))

    quote_section = re.search(
        r"FINAL RECOMMENDED QUOTE(?P<body>.*?)(?:ASSESSMENT CONFIDENCE|GO\s*/\s*NO-GO|$)",
        final,
        re.I | re.S,
    )
    if quote_section:
        body = quote_section.group("body")
        has_amount = bool(re.search(r"(?:₹|INR|Rs\.?)[ \t]*[\d,]+", body, re.I))
        safely_withheld = bool(re.search(r"NOT CALCULABLE FROM SUPPLIED EVIDENCE", body, re.I))
        evidence_lower = tender_text.casefold()
        has_verified_quote_inputs = (
            "verified cost" in evidence_lower
            and bool(re.search(r"\b(?:gst|tax treatment|tax rate)\b", evidence_lower))
            and "margin" in evidence_lower
        )
        if has_amount and not safely_withheld and not has_verified_quote_inputs:
            issues.append(QualityIssue(
                "unsafe_quote", "critical",
                "The report recommends a monetary quote without passing the verified-cost safety gate.",
            ))

    payment_section = re.search(
        r"(?:^|\n)#{0,3}\s*PAYMENT\s+(?:MILESTONES|TERMS|SCHEDULE)(?P<body>.*?)(?=\n#{1,3}\s|\Z)",
        final,
        re.I | re.S,
    )
    if payment_section:
        percentages = [float(value) for value in re.findall(r"(\d+(?:\.\d+)?)\s*%", payment_section.group("body"))]
        if len(percentages) >= 2 and abs(sum(percentages) - 100.0) > 0.01:
            issues.append(QualityIssue(
                "payment_percentages_invalid", "critical",
                f"Payment milestones total {sum(percentages):g}% instead of 100%.",
            ))

    # De-duplicate equivalent findings to keep the customer-facing message concise.
    unique: dict[tuple[str, str], QualityIssue] = {}
    for issue in issues:
        unique[(issue.code, issue.message)] = issue
    return list(unique.values())


def correction_brief(issues: list[QualityIssue]) -> str:
    return "\n".join(f"- {issue.message}" for issue in issues)


def blocked_report(issues: list[QualityIssue]) -> str:
    """Return a safe customer-facing artifact when synthesis fails QA twice."""
    lines = [
        "## REPORT BLOCKED — QUALITY REVIEW REQUIRED",
        "",
        "Unique Type did not release the generated recommendation because deterministic checks found unsupported or contradictory claims.",
        "",
        "### Issues detected",
    ]
    lines.extend(f"- {issue.message}" for issue in issues)
    lines.extend([
        "",
        "### Status",
        "No GO/NO-GO decision or recommended quote is released from this run. Retry after the evidence and agent outputs are corrected.",
    ])
    return "\n".join(lines)
