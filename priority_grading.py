#!/usr/bin/env python3
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Sequence, Tuple


PRIORITY_ORDER = ("S", "A", "B", "C")
DOMAIN_ORDER = (
    "CCM",
    "Venous malformation",
    "Brain AVM / AVM",
    "Other vascular malformation",
    "Cross-domain vascular biology",
    "Out-of-scope",
)

# Standalone "CCM" and "CM" are deliberately absent. They are ambiguous biomedical
# acronyms (for example corneal confocal microscopy and cirrhotic cardiomyopathy).
CCM_STRONG_PATTERNS = (
    r"\bcerebral cavernous malformations?\b",
    r"\bbrain cavernous malformations?\b",
    r"\bintracranial cavernous malformations?\b",
    r"\bspinal cavernous malformations?\b",
    r"\bspinal cord cavernous malformations?\b",
    r"\bintramedullary cavernous malformations?\b",
    r"\b(?:cerebral|brain|intracranial|spinal|spinal cord|intramedullary|cns) cavernomas?\b",
    r"\bcerebral cavernomas?\b",
    r"\bbrain cavernomas?\b",
    r"\bkrit1\b",
    r"\bccm1\b",
    r"\bccm2\b",
    r"\bpdcd10\b",
    r"\bccm3\b",
)
VENOUS_MALFORMATION_PATTERNS = (
    r"\bvenous malformations?\b",
    r"\bslow[- ]flow (?:venous|vascular) malformations?\b",
    r"\bpik3ca[- ](?:associated|related) (?:venous )?malformations?\b",
)
AVM_PATTERNS = (
    r"\b(?:brain|cerebral) arteriovenous malformations?\b",
    r"\b(?:brain|cerebral) avms?\b",
    r"\barteriovenous malformations?\b",
)
OTHER_MALFORMATION_PATTERNS = (
    r"\blymphatic malformations?\b",
    r"\bcapillary malformations?\b",
    r"\bcombined (?:vascular )?malformations?\b",
    r"\bcapillary[- ]venous malformations?\b",
    r"\bpik3ca[- ]related (?:overgrowth spectrum|vascular anomal(?:y|ies))\b",
    r"\bvascular anomal(?:y|ies)\b",
    r"\bvascular malformations?\b",
)

QSM_PATTERNS = (
    r"\bqsm\b",
    r"\bquantitative susceptibility mapping\b",
    r"\bquantitative susceptibility\b",
    r"\bmagnetic susceptibility\b",
    r"\bsusceptibility mapping\b",
    r"\bdelta[- ]?qsm\b",
    r"δ\s*qsm\b",
    r"\bqsm changes?\b",
    r"\blongitudinal qsm\b",
)
TRIAL_PATTERNS = (
    r"\brct\b",
    r"\brandomi[sz]ed(?: controlled)? trials?\b",
    r"\bclinical trials?\b",
    r"\bphase\s+(?:i|ii|iii|1|2|3)(?:\s*/\s*(?:i|ii|iii|1|2|3))?\b",
    r"\bplacebo[- ]controlled\b",
    r"\btrial[- ]readiness\b",
    r"\btrial[- ]ready\b",
    r"\bat cash epoc\b",
    r"\bcare trial\b",
    r"\brec[- ]994 trial\b",
    r"\b(?:rapamycin|sirolimus) trial\b",
    r"\beverolimus trials?\b",
)

OMICS_PATTERNS = (
    r"\bsingle[- ]cell\b",
    r"\bscrna[- ]?seq\b",
    r"\bspatial transcriptom(?:e|ic|ics)\b",
    r"\brna[- ]?seq\b",
    r"\btranscriptom(?:e|ic|ics)\b",
    r"\bproteom(?:e|es|ic|ics)\b",
    r"\bmetabolom(?:e|es|ic|ics)\b",
    r"\bmulti[- ]omics\b",
    r"\bgenomics\b",
    r"\bepigenomics\b",
    r"\bspatial[- ]omics\b",
    r"\bbioinformatics\b",
)

SIGNALING_PATTERNS = (
    r"\bpi3k(?:[- /]akt)?(?:[- /]mtor)?\b",
    r"\bpik3ca\b",
    r"\bakt[123]?\b",
    r"\bmtor\b",
    r"\bmap3k3\b",
    r"\bmekk3\b",
    r"\bklf2\b",
    r"\bklf4\b",
    r"\brhoa\b",
    r"\brock[12]?\b",
    r"\bmapk\b",
    r"\bhif1a\b",
    r"\bhif[- ]?1(?:alpha)?\b",
    r"\bepas1\b",
    r"\bhif[- ]?2(?:alpha)?\b",
    r"\bhypoxi(?:a|c)\b",
    r"\btek\b",
    r"\btie2\b",
    r"\bkras\b",
    r"\bbraf\b",
)

CELL_AND_METABOLISM_PATTERNS = (
    r"\bmacrophages?\b",
    r"\bmicroglia\b",
    r"\bpericytes?\b",
    r"\bfibroblasts?\b",
    r"\biron metabolism\b",
    r"\bhemosiderin\b",
    r"\bferroptosis\b",
    r"\bglycolysis\b",
    r"\bmitochondri(?:a|al|on)\b",
    r"\bmetabolic reprogramming\b",
)

# Precise immune concepts only. Technique-only words such as immunohistochemistry,
# immunostaining and immunofluorescence intentionally do not match this list.
IMMUNE_CONCEPT_PATTERNS = (
    r"\bimmune\b",
    r"\bimmunity\b",
    r"\bimmunology\b",
    r"\bimmunological\b",
    r"\bimmune responses?\b",
    r"\bimmune cells?\b",
    r"\bimmune[- ]mediated\b",
    r"\bimmunomodulatory\b",
    r"\bimmunosuppressive\b",
    r"\binflamm(?:ation|atory)\b",
    r"\bneuroinflammation\b",
)

ENDOTHELIAL_MECHANISM_PATTERNS = (
    r"\bendothelial dysfunction\b",
    r"\bendothelial (?:cell[- ]cell )?junctions?\b",
    r"\bblood[- ]brain barrier\b",
    r"\b(?:bbb|vascular) permeability\b",
    r"\bangiogenesis\b",
    r"\bvascular remodel(?:ing|ling)\b",
    r"\bsomatic mutations?\b",
    r"\bclonal mutations?\b",
    r"\bmosaic mutations?\b",
    r"\bmacrophage[- ]endothelial (?:interaction|crosstalk)\b",
    r"\bimmune[- ]endothelial (?:interaction|crosstalk)\b",
    r"\bmtor feedback\b",
    r"\bpi3k inhibitor resistance\b",
    r"\bdrug resistance\b",
    r"\btargeted therap(?:y|ies)\b",
)

MECHANISM_WHITELIST_PATTERNS = (
    *SIGNALING_PATTERNS,
    *CELL_AND_METABOLISM_PATTERNS,
    *IMMUNE_CONCEPT_PATTERNS,
    *ENDOTHELIAL_MECHANISM_PATTERNS,
)

VASCULAR_CONTEXT_PATTERNS = (
    r"\bendotheli(?:al|um)\b",
    r"\bvasculature\b",
    r"\bblood[- ]brain barrier\b",
    r"\b(?:brain )?microvascul(?:ar|ature)\b",
    r"\bvascular permeability\b",
    r"\bangiogenesis\b",
    r"\bvascular remodel(?:ing|ling)\b",
    r"\bneurovascular\b",
    r"\b(?:retinal|pulmonary|tumou?r) vasculature\b",
    r"\b(?:retinal|pulmonary) vascular (?:disease|biology)\b",
    r"\btumou?r vascular biology\b",
    r"\bvascular inflammation\b",
    r"\bvascular biology\b",
)

TARGETED_THERAPY_PATTERNS = (
    r"\bsirolimus\b",
    r"\brapamycin\b",
    r"\beverolimus\b",
    r"\balpelisib\b",
    r"\btargeted therap(?:y|ies)\b",
    r"\bpi3k inhibitors?\b",
    r"\bmtor inhibitors?\b",
)

CCM_DRUG_PATTERNS = (
    *TARGETED_THERAPY_PATTERNS,
    r"\brec[- ]994\b",
    r"\bpropranolol\b",
    r"\baspirin\b",
    r"\batorvastatin\b",
    r"\bfasudil\b",
    r"\bvitamin d\b",
)

CCM_CORE_PATTERNS = (
    *OMICS_PATTERNS,
    *MECHANISM_WHITELIST_PATTERNS,
    *CCM_DRUG_PATTERNS,
    r"\bendothelial biology\b",
    r"\bendothelial metabolism\b",
    r"\bendotheli(?:al|um)\b",
    r"\bpathogenesis\b",
    r"\bmechanis(?:m|ms|tic)\b",
)

PLASMA_EXCHANGE_PATTERNS = (
    r"\b(?:therapeutic )?plasma exchange\b",
    r"\bplasmapheresis\b",
    r"\bblood exchange\b",
    r"\bexchange transfusion\b",
    r"\bred cell exchange\b",
    r"\bimmunoadsorption\b",
)

CLINICAL_PATTERNS = (
    r"\bnatural history\b",
    r"\bcohorts?\b",
    r"\bprospective\b",
    r"\bretrospective\b",
    r"\bregistr(?:y|ies)\b",
    r"\bfollow[- ]up\b",
    r"\bprognosis\b",
    r"\bhemorrhag(?:e|es|ic)\b",
    r"\bhaemorrhag(?:e|es|ic)\b",
    r"\bbleeding\b",
    r"\bepilep(?:sy|tic)\b",
    r"\bseizures?\b",
    r"\boutcomes?\b",
    r"\bsurger(?:y|ies|ical)\b",
    r"\bresection\b",
    r"\bquality of life\b",
    r"\bpatient[- ]reported outcomes?\b",
    r"\bpro\b",
    r"\bmrs\b",
    r"\bstereotactic radiosurgery\b",
    r"\bradiosurgery\b",
    r"\bswi\b",
    r"\bdce\b",
    r"\bradiomics\b",
    r"\bmachine[- ]learning\b",
    r"\brisk prediction\b",
    r"\bmagnetic resonance imaging\b",
    r"\bmri\b",
    r"\bneuroimaging\b",
    r"\bimaging\b",
)


def normalize_text(*values: object) -> str:
    text = " ".join(str(value or "") for value in values)
    text = unicodedata.normalize("NFKC", text).casefold()
    text = text.replace("α", "alpha")
    text = re.sub(r"[‐‑‒–—−]", "-", text)
    return re.sub(r"\s+", " ", text).strip()


def matches_any(text: str, patterns: Sequence[str]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def is_plasma_exchange_text(*values: object) -> bool:
    return matches_any(normalize_text(*values), PLASMA_EXCHANGE_PATTERNS)


def mechanism_labels(*values: object) -> List[str]:
    text = normalize_text(*values)
    groups = (
        ("PI3K-AKT-mTOR / targeted therapy", (*SIGNALING_PATTERNS[:4], *TARGETED_THERAPY_PATTERNS)),
        ("MAP3K3-MEKK3 / KLF2-KLF4 / RhoA-ROCK / MAPK", SIGNALING_PATTERNS[4:11]),
        ("HIF / hypoxia / endothelial-barrier biology", (*SIGNALING_PATTERNS[11:16], *ENDOTHELIAL_MECHANISM_PATTERNS[:6])),
        ("TEK-TIE2 / somatic-mosaic vascular signaling", (*SIGNALING_PATTERNS[16:], *ENDOTHELIAL_MECHANISM_PATTERNS[6:9])),
        ("immune-endothelial / neuroinflammation", (*IMMUNE_CONCEPT_PATTERNS, r"\bmacrophages?\b", r"\bmicroglia\b")),
        ("iron / hemosiderin / ferroptosis", CELL_AND_METABOLISM_PATTERNS[4:7]),
        ("glycolysis / mitochondria / metabolic reprogramming", CELL_AND_METABOLISM_PATTERNS[7:]),
        ("omics / bioinformatics", OMICS_PATTERNS),
        ("mTOR feedback / inhibitor resistance", ENDOTHELIAL_MECHANISM_PATTERNS[11:]),
    )
    return [label for label, patterns in groups if matches_any(text, patterns)]


def classify_domain(
    title: str = "",
    abstract: str = "",
    topic: str = "",
    journal: str = "",
) -> Tuple[str, str]:
    """Classify disease domain from article evidence; topic is not disease evidence."""
    del topic
    text = normalize_text(title, abstract, journal)

    if matches_any(text, CCM_STRONG_PATTERNS):
        return "CCM", "Strong CCM disease/gene expression in title or abstract"
    if matches_any(text, AVM_PATTERNS):
        return "Brain AVM / AVM", "Arteriovenous malformation expression in article content"
    if matches_any(text, (r"\btek\b", r"\btie2\b")) and matches_any(
        text,
        (*VENOUS_MALFORMATION_PATTERNS, *OTHER_MALFORMATION_PATTERNS),
    ):
        return "Venous malformation", "TEK/TIE2 appears with vascular-malformation context"
    if matches_any(text, VENOUS_MALFORMATION_PATTERNS):
        return "Venous malformation", "Venous or slow-flow malformation expression in article content"
    if matches_any(text, OTHER_MALFORMATION_PATTERNS):
        return "Other vascular malformation", "Other vascular malformation/anomaly expression in article content"

    has_mechanism = matches_any(text, MECHANISM_WHITELIST_PATTERNS)
    has_vascular_context = matches_any(text, VASCULAR_CONTEXT_PATTERNS)
    if has_mechanism and has_vascular_context:
        return (
            "Cross-domain vascular biology",
            "Transferable mechanism appears with explicit vascular/endothelial context",
        )

    return "Out-of-scope", "No strong CCM/vascular-malformation or transferable vascular mechanism evidence"


def classify_translational_relevance(
    title: str = "",
    abstract: str = "",
    topic: str = "",
    journal: str = "",
    domain: str | None = None,
) -> Tuple[str, str]:
    text = normalize_text(title, abstract, journal)
    resolved_domain = domain or classify_domain(title, abstract, topic, journal)[0]

    if resolved_domain == "CCM":
        return "Direct", "The article has strong direct CCM evidence"

    if is_plasma_exchange_text(text):
        return (
            "Exploratory",
            "Independent plasma exchange/blood exchange research interest; not disease-domain relevance",
        )

    related_domains = {"Venous malformation", "Brain AVM / AVM", "Other vascular malformation"}
    if resolved_domain in related_domains:
        if matches_any(text, (*MECHANISM_WHITELIST_PATTERNS, *TARGETED_THERAPY_PATTERNS)):
            return "Strong", "Related vascular malformation with a transferable mechanism or targeted therapy"
        return "Moderate", "Related vascular malformation without a strong targeted mechanism signal"

    if resolved_domain == "Cross-domain vascular biology":
        high_value = matches_any(
            text,
            (
                *ENDOTHELIAL_MECHANISM_PATTERNS,
                r"\bendotheli(?:al|um)\b.*\b(?:hif|hypoxi|glycolysis|mitochondri)",
                r"\b(?:hif|hypoxi|glycolysis|mitochondri).*\bendotheli(?:al|um)\b",
                r"\b(?:iron|hemosiderin|ferroptosis)\b.*\bvascular\b",
            ),
        )
        if high_value:
            return "Moderate", "Different disease with a highly transferable vascular/endothelial mechanism"
        return "Exploratory", "Cross-domain vascular mechanism with exploratory CCM relevance"

    return "Low", "Only generic or out-of-scope keyword overlap"


def grade_priority(
    title: str = "",
    abstract: str = "",
    topic: str = "",
    journal: str = "",
    domain: str | None = None,
    translational_relevance: str | None = None,
) -> Tuple[str, str]:
    """Assign S/A/B/C with deterministic ordered rules; topic never creates S."""
    text = normalize_text(title, abstract, journal)
    resolved_domain = domain or classify_domain(title, abstract, topic, journal)[0]
    relevance = translational_relevance or classify_translational_relevance(
        title, abstract, topic, journal, resolved_domain
    )[0]

    if resolved_domain == "CCM" and matches_any(text, QSM_PATTERNS):
        return "S", "S: strong CCM evidence + QSM"
    if resolved_domain == "CCM" and matches_any(text, TRIAL_PATTERNS):
        return "S", "S: strong CCM evidence + clinical trial/trial readiness"

    if is_plasma_exchange_text(text):
        return "A", "A: plasma exchange/plasmapheresis/blood exchange/immunoadsorption"

    if resolved_domain == "CCM" and matches_any(
        text,
        CCM_CORE_PATTERNS,
    ):
        return "A", "A: CCM core omics/mechanism"

    related_domains = {"Venous malformation", "Brain AVM / AVM", "Other vascular malformation"}
    if resolved_domain in related_domains and matches_any(
        text,
        (*MECHANISM_WHITELIST_PATTERNS, *CCM_DRUG_PATTERNS),
    ):
        return "A", "A: related vascular malformation + transferable mechanism/targeted therapy"

    if resolved_domain == "Cross-domain vascular biology" and relevance == "Moderate":
        return "A", "A: highly transferable cross-domain vascular mechanism"

    if resolved_domain in ({"CCM"} | related_domains) and matches_any(text, CLINICAL_PATTERNS):
        return "B", "B: CCM/related vascular-malformation clinical evidence"

    return "C", "C: broad, exploratory, low-relevance, or unmatched article"


def classify_literature(
    title: str = "",
    abstract: str = "",
    topic: str = "",
    journal: str = "",
) -> Dict[str, str]:
    special_interest = (
        "Plasma exchange / blood exchange"
        if is_plasma_exchange_text(title, abstract, journal)
        else ""
    )
    domain, domain_reason = classify_domain(title, abstract, topic, journal)
    relevance, relevance_reason = classify_translational_relevance(
        title, abstract, topic, journal, domain
    )
    if special_interest and "independent" not in relevance_reason.casefold():
        relevance_reason = (
            f"{relevance_reason}; also tracked as an independent plasma exchange/blood exchange interest"
        )
    priority, priority_reason = grade_priority(
        title,
        abstract,
        topic,
        journal,
        domain=domain,
        translational_relevance=relevance,
    )
    return {
        "special_interest": special_interest,
        "domain": domain,
        "domain_reason": domain_reason,
        "translational_relevance": relevance,
        "translational_reason": relevance_reason,
        "priority": priority,
        "priority_reason": priority_reason,
    }
