from __future__ import annotations

from collections import OrderedDict
from typing import Any, Dict, List, Sequence

from priority_grading import PRIORITY_ORDER, is_plasma_exchange_text, mechanism_labels


RELATED_DOMAINS = (
    "Venous malformation",
    "Brain AVM / AVM",
    "Other vascular malformation",
)


def _article_lines(article: Dict[str, Any], heading_level: int = 3) -> List[str]:
    hashes = "#" * heading_level
    lines = [
        "",
        f"{hashes} [{article.get('priority', 'C')}] {article.get('title') or '[No title]'}",
        "",
        f"- PMID: {article.get('pmid') or '未提供'}",
        f"- Domain: {article.get('domain') or '未提供'}",
        f"- Domain 依据: {article.get('domain_reason') or '未提供'}",
        f"- 转化相关性: {article.get('translational_relevance') or '未提供'}",
        f"- 转化相关性依据: {article.get('translational_reason') or '未提供'}",
        f"- 优先级依据: {article.get('priority_reason') or '未提供'}",
        f"- 主题: {article.get('topic') or '未提供'}",
        f"- 来源类型: {article.get('source_type') or '未提供'}",
    ]
    if article.get("source_note"):
        lines.append(f"- 来源说明: {article['source_note']}")
    lines.extend(
        [
            f"- 期刊: {article.get('journal') or '未提供'}",
            f"- 作者: {article.get('authors') or '未提供'}",
            f"- 发表日期: {article.get('publication_date') or '未提供'}",
            f"- DOI: {article.get('doi') or '未提供'}",
            f"- PubMed: {article.get('pubmed_url') or '未提供'}",
        ]
    )
    if article.get("daily_report_date"):
        lines.append(f"- 日报日期: {article['daily_report_date']}")
    lines.extend(["", "#### 摘要", "", str(article.get("abstract") or "PubMed 未提供摘要。")])
    return lines


def _append_grouped_articles(
    lines: List[str],
    articles: Sequence[Dict[str, Any]],
    group_key: str,
    group_order: Sequence[str],
) -> None:
    for value in group_order:
        selected = [article for article in articles if article.get(group_key) == value]
        if not selected:
            continue
        lines.extend(["", f"### {value}（{len(selected)}）"])
        for article in selected:
            lines.extend(_article_lines(article, heading_level=4))


def build_structured_markdown(
    title: str,
    period_line: str,
    records: Sequence[Dict[str, Any]],
    empty_text: str,
) -> str:
    """Build the shared deterministic Daily/Weekly knowledge-oriented layout."""
    counts = {priority: sum(r.get("priority") == priority for r in records) for priority in PRIORITY_ORDER}
    lines = [
        f"# {title}",
        "",
        period_line,
        "",
        f"共汇总 {len(records)} 篇去重文献。",
        "",
        "| 优先级 | 数量 |",
        "| --- | ---: |",
    ]
    lines.extend(f"| {priority} | {counts[priority]} |" for priority in PRIORITY_ORDER)

    if not records:
        lines.extend(["", empty_text])
        return "\n".join(lines) + "\n"

    ccm = [article for article in records if article.get("domain") == "CCM"]
    lines.extend(["", f"## 1. CCM 核心进展（{len(ccm)}）"])
    if ccm:
        _append_grouped_articles(lines, ccm, "priority", PRIORITY_ORDER)
    else:
        lines.extend(["", "本期无 CCM 核心文献。"])

    related = [article for article in records if article.get("domain") in RELATED_DOMAINS]
    lines.extend(["", f"## 2. Related vascular malformations（{len(related)}）"])
    if related:
        _append_grouped_articles(lines, related, "domain", RELATED_DOMAINS)
    else:
        lines.extend(["", "本期无相关血管畸形文献。"])

    transferable: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
    for article in records:
        if article.get("translational_relevance") not in {"Strong", "Moderate"}:
            continue
        for label in mechanism_labels(article.get("title"), article.get("abstract")):
            transferable.setdefault(label, []).append(article)
    transferable_count = len({a.get("pmid") for values in transferable.values() for a in values})
    lines.extend(["", f"## 3. 可迁移机制与药物（{transferable_count}）"])
    if transferable:
        for label, articles in transferable.items():
            lines.extend(["", f"### {label}（{len(articles)}）"])
            for article in articles:
                lines.extend(_article_lines(article, heading_level=4))
    else:
        lines.extend(["", "本期无 Strong/Moderate 可迁移机制文献。"])

    plasma = [
        article
        for article in records
        if is_plasma_exchange_text(article.get("title"), article.get("abstract"))
    ]
    lines.extend(["", f"## 4. 血浆置换 / 换血（{len(plasma)}）"])
    if plasma:
        for article in plasma:
            lines.extend(_article_lines(article))
    else:
        lines.extend(["", "本期无血浆置换、免疫吸附或换血文献。"])

    cross_domain = [
        article
        for article in records
        if article.get("domain") == "Cross-domain vascular biology"
        and article.get("source_type") == "顶刊扩展"
        and article.get("translational_relevance") in {"Moderate", "Exploratory"}
    ]
    lines.extend(["", f"## 5. 跨领域顶刊启发（{len(cross_domain)}）"])
    if cross_domain:
        for article in cross_domain:
            lines.extend(_article_lines(article))
    else:
        lines.extend(["", "本期无通过机制白名单筛选的跨领域顶刊文献。"])

    low_relevance = [
        article
        for article in records
        if article.get("domain") == "Out-of-scope"
        or (
            article.get("domain") == "Cross-domain vascular biology"
            and article.get("pmid") not in {item.get("pmid") for item in cross_domain}
            and article.get("translational_relevance") not in {"Strong", "Moderate"}
        )
    ]
    lines.extend(["", f"## 6. 低相关性 / 范围外记录（{len(low_relevance)}）"])
    if low_relevance:
        for article in low_relevance:
            lines.extend(_article_lines(article))
    else:
        lines.extend(["", "本期无低相关性或范围外记录。"])

    return "\n".join(lines) + "\n"
