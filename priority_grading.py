#!/usr/bin/env python3
from __future__ import annotations

import re
import unicodedata
from typing import Sequence, Tuple


PRIORITY_ORDER = ("S", "A", "B", "C")

CM_CONTENT_PATTERNS = (
    r"\bcerebral cavernous malformations?\b",
    r"\bcavernous malformations?\b",
    r"\bccm(?:s|[123])?\b",
    r"(?<![a-z0-9])cm(?![a-z0-9])",
)
CM_TOPIC_PATTERNS = CM_CONTENT_PATTERNS + (
    r"(?:ccm|cm)\s*基础机制",
)
QSM_PATTERNS = (r"\bqsm\b", r"\bquantitative susceptibility mapping\b")
TRIAL_PATTERNS = (
    r"\brct\b",
    r"\brandomi[sz]ed\b.*\btrial\b",
    r"\bclinical trials?\b",
    r"\btrial[- ]readiness\b",
    r"\btrial[- ]ready\b",
)
CCM_MECHANISM_PATTERNS = (
    r"\bmechanis(?:m|ms|tic)\b",
    r"\bpathogenesis\b",
    r"\bendotheli(?:al|um)\b",
    r"\bblood[- ]brain barrier\b",
    r"\bkrit1\b",
    r"\bccm[123]\b",
    r"\bpdcd10\b",
    r"\bklf4\b",
    r"\bmekk3\b",
    r"\brhoa\b",
)

A_RULES = (
    ("single-cell", (r"\bsingle[- ]cell\b", r"\bscrna[- ]?seq\b")),
    ("spatial transcriptomics", (r"\bspatial transcriptom(?:e|ic|ics)\b",)),
    ("RNA-seq", (r"\brna[- ]?seq\b", r"\brnaseq\b")),
    ("proteomics", (r"\bproteom(?:e|es|ic|ics)\b",)),
    ("metabolomics", (r"\bmetabolom(?:e|es|ic|ics)\b",)),
    ("multi-omics", (r"\bmulti[- ]omics\b", r"\bmultiomics\b")),
    ("mTOR/PI3K-AKT", (r"\bmtor\b", r"\bpi3k\b", r"\bpik3ca\b", r"\bakt[123]?\b")),
    ("HIF1A/HIF-1α", (r"\bhif1a\b", r"\bhif[- ]?1(?:alpha)?\b")),
    ("EPAS1/HIF-2α", (r"\bepas1\b", r"\bhif[- ]?2(?:alpha)?\b")),
    (
        "immune/inflammation/metabolism",
        (r"\bimmun[a-z0-9-]*\b", r"\binflamm(?:ation|atory)\b", r"\bmetaboli(?:sm|c)\b"),
    ),
    (
        "plasma exchange / plasmapheresis / blood exchange",
        (
            r"\b(?:therapeutic )?plasma exchange\b",
            r"\bplasmapheresis\b",
            r"\bblood exchange\b",
            r"\bexchange transfusion\b",
            r"\bred cell exchange\b",
        ),
    ),
)

B_RULES = (
    ("natural history", (r"\bnatural history\b",)),
    ("cohort", (r"\bcohorts?\b",)),
    ("hemorrhage", (r"\bhemorrhag(?:e|es|ic)\b", r"\bhaemorrhag(?:e|es|ic)\b", r"\bbleeding\b")),
    ("epilepsy", (r"\bepilep(?:sy|tic)\b", r"\bseizures?\b")),
    ("outcome", (r"\boutcomes?\b",)),
    ("surgery", (r"\bsurger(?:y|ies|ical)\b", r"\bresection\b")),
    (
        "general clinical imaging",
        (
            r"\bmagnetic resonance imaging\b",
            r"\bmri\b",
            r"\bneuroimaging\b",
            r"\bradiolog(?:y|ical)\b",
            r"\bimaging\b",
        ),
    ),
)

C_RULES = (
    ("broad review/background", (r"\breviews?\b", r"\bbackground\b", r"\boverview\b")),
)


def normalize_text(*values: object) -> str:
    text = " ".join(str(value or "") for value in values)
    text = unicodedata.normalize("NFKC", text).casefold()
    text = text.replace("α", "alpha")
    text = re.sub(r"[‐‑‒–—−]", "-", text)
    return re.sub(r"\s+", " ", text).strip()


def matches_any(text: str, patterns: Sequence[str]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def grade_priority(
    title: str = "",
    abstract: str = "",
    topic: str = "",
    journal: str = "",
) -> Tuple[str, str]:
    """Assign S/A/B/C using deterministic, ordered rules only."""
    article_text = normalize_text(title, abstract, journal)
    topic_text = normalize_text(topic)
    combined_text = normalize_text(article_text, topic_text)

    has_cm_context = matches_any(article_text, CM_CONTENT_PATTERNS) or matches_any(
        topic_text, CM_TOPIC_PATTERNS
    )

    if has_cm_context and matches_any(article_text, QSM_PATTERNS):
        return "S", "S: CM/CCM + QSM"

    if has_cm_context and matches_any(article_text, TRIAL_PATTERNS):
        return "S", "S: CM/CCM + RCT/clinical trial/trial readiness"

    if matches_any(topic_text, (r"(?:ccm|cm)\s*基础机制",)) or (
        has_cm_context and matches_any(article_text, CCM_MECHANISM_PATTERNS)
    ):
        return "A", "A: CCM基础机制"

    for label, patterns in A_RULES:
        if matches_any(combined_text, patterns):
            return "A", f"A: {label}"

    for label, patterns in B_RULES:
        if matches_any(combined_text, patterns):
            return "B", f"B: {label}"

    for label, patterns in C_RULES:
        if matches_any(combined_text, patterns):
            return "C", f"C: {label}"

    return "C", "C: no S/A/B priority signal matched"
