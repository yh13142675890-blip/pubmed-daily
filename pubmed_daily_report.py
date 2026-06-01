#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import smtplib
import ssl
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter, OrderedDict
from dataclasses import dataclass
from email.mime.text import MIMEText
from email.utils import formatdate
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import requests
import yaml


EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"

CLASSIC_FILTER = """
("review"[Publication Type]
OR "systematic review"[Publication Type]
OR "meta-analysis"[Publication Type]
OR "clinical trial"[Publication Type]
OR "guideline"[Publication Type]
OR "practice guideline"[Publication Type])
"""


@dataclass
class Article:
    pmid: str
    title: str
    abstract: str
    authors: str
    journal: str
    pub_date: str
    doi: str
    url: str
    topic: str
    source_type: str
    source_note: str = ""
    summary: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PubMed grouped daily report with fallback filling")

    parser.add_argument("--query-config", default="pubmed_topics.yml")
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--lookback-days", type=int, default=180)
    parser.add_argument("--classic-lookback-days", type=int, default=3650)
    parser.add_argument("--per-topic-count", type=int, default=10)
    parser.add_argument("--max-results", type=int, default=800)
    parser.add_argument("--dedupe-file", default="data/seen_pmids.json")
    parser.add_argument("--summary-language", default="zh", choices=["zh", "en"])
    parser.add_argument("--enable-fallback-fill", default="true")
    parser.add_argument("--ai-summarize-per-topic", type=int, default=0)
    parser.add_argument("--push", default="smtp", choices=["smtp", "none"])

    return parser.parse_args()


def as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def require_env(name: str) -> str:
    value = os.getenv(name, "")
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def today_utc() -> dt.date:
    return dt.datetime.utcnow().date()


def date_range(days: int) -> Tuple[str, str]:
    end = today_utc()
    start = end - dt.timedelta(days=max(days - 1, 0))
    return start.strftime("%Y/%m/%d"), end.strftime("%Y/%m/%d")


def load_config(path: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Topic config not found: {path}")

    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    topics = []
    for item in data.get("topics", []):
        name = str(item.get("name", "")).strip()
        query = str(item.get("query", "")).strip()
        count = int(item.get("per_topic_count", 10))
        if name and query:
            topics.append({"name": name, "query": query, "per_topic_count": count})

    fallback_topics = []
    for item in data.get("fallback_topics", []):
        name = str(item.get("name", "")).strip()
        query = str(item.get("query", "")).strip()
        if name and query:
            fallback_topics.append({"name": name, "query": query})

    if not topics:
        raise ValueError("No valid topics found in pubmed_topics.yml")

    return topics, fallback_topics


def load_seen(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"global_seen_pmids": [], "by_topic": {}, "updated_at": None}

    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {"global_seen_pmids": [], "by_topic": {}, "updated_at": None}

    data.setdefault("global_seen_pmids", [])
    data.setdefault("by_topic", {})
    data.setdefault("updated_at", None)
    return data


def save_seen(path: str, data: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    data["updated_at"] = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"

    global_seen = list(OrderedDict.fromkeys(str(x) for x in data.get("global_seen_pmids", [])))
    data["global_seen_pmids"] = global_seen[-50000:]

    by_topic = data.get("by_topic", {})
    for topic, pmids in list(by_topic.items()):
        cleaned = list(OrderedDict.fromkeys(str(x) for x in pmids))
        by_topic[topic] = cleaned[-10000:]
    data["by_topic"] = by_topic

    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def ncbi_common_params() -> Dict[str, str]:
    params: Dict[str, str] = {}
    email = os.getenv("NCBI_EMAIL", "")
    api_key = os.getenv("NCBI_API_KEY", "")

    if email:
        params["email"] = email
    if api_key:
        params["api_key"] = api_key

    return params


def esearch_pubmed(query: str, days: int, max_results: int) -> List[str]:
    mindate, maxdate = date_range(days)

    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": str(max_results),
        "sort": "pub date",
        "datetype": "pdat",
        "mindate": mindate,
        "maxdate": maxdate,
    }
    params.update(ncbi_common_params())

    response = requests.get(f"{EUTILS_BASE}/esearch.fcgi", params=params, timeout=60)
    response.raise_for_status()
    data = response.json()
    return [str(x) for x in data.get("esearchresult", {}).get("idlist", [])]


def efetch_pubmed(pmids: Sequence[str], topic: str, source_type: str, source_note: str = "") -> List[Article]:
    if not pmids:
        return []

    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
    }
    params.update(ncbi_common_params())

    response = requests.get(f"{EUTILS_BASE}/efetch.fcgi", params=params, timeout=80)
    response.raise_for_status()

    root = ET.fromstring(response.text)
    articles: List[Article] = []

    for node in root.findall(".//PubmedArticle"):
        article = parse_pubmed_article(node, topic=topic, source_type=source_type, source_note=source_note)
        if article:
            articles.append(article)

    article_map = {a.pmid: a for a in articles}
    return [article_map[pmid] for pmid in pmids if pmid in article_map]


def get_text(elem: Optional[ET.Element]) -> str:
    if elem is None:
        return ""
    text = "".join(elem.itertext())
    text = re.sub(r"\s+", " ", text).strip()
    return html.unescape(text)


def parse_pubmed_article(
    pubmed_article: ET.Element,
    topic: str,
    source_type: str,
    source_note: str = "",
) -> Optional[Article]:
    pmid = get_text(pubmed_article.find(".//PMID"))
    if not pmid:
        return None

    title = get_text(pubmed_article.find(".//ArticleTitle")) or "[No title]"

    abstract_parts = []
    for abstract_text in pubmed_article.findall(".//Abstract/AbstractText"):
        label = abstract_text.attrib.get("Label", "").strip()
        part = get_text(abstract_text)
        if label and part:
            abstract_parts.append(f"{label}: {part}")
        elif part:
            abstract_parts.append(part)
    abstract = "\n".join(abstract_parts).strip()

    journal = get_text(pubmed_article.find(".//Journal/Title"))
    if not journal:
        journal = get_text(pubmed_article.find(".//Journal/ISOAbbreviation"))

    return Article(
        pmid=pmid,
        title=title,
        abstract=abstract,
        authors=parse_authors(pubmed_article),
        journal=journal or "[No journal]",
        pub_date=parse_pub_date(pubmed_article),
        doi=parse_doi(pubmed_article),
        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        topic=topic,
        source_type=source_type,
        source_note=source_note,
    )


def parse_authors(pubmed_article: ET.Element, limit: int = 6) -> str:
    names = []
    for author in pubmed_article.findall(".//AuthorList/Author"):
        collective = get_text(author.find("CollectiveName"))
        if collective:
            names.append(collective)
            continue

        last = get_text(author.find("LastName"))
        initials = get_text(author.find("Initials"))
        if last and initials:
            names.append(f"{last} {initials}")
        elif last:
            names.append(last)

    if not names:
        return ""
    return ", ".join(names[:limit]) + (", et al." if len(names) > limit else "")


def parse_pub_date(pubmed_article: ET.Element) -> str:
    pub_date = pubmed_article.find(".//JournalIssue/PubDate")
    if pub_date is None:
        return ""

    year = get_text(pub_date.find("Year"))
    month = get_text(pub_date.find("Month"))
    day = get_text(pub_date.find("Day"))
    medline = get_text(pub_date.find("MedlineDate"))

    parts = [x for x in [year, month, day] if x]
    return " ".join(parts) if parts else medline


def parse_doi(pubmed_article: ET.Element) -> str:
    for article_id in pubmed_article.findall(".//ArticleIdList/ArticleId"):
        if article_id.attrib.get("IdType", "").lower() == "doi":
            return get_text(article_id)
    return ""


def unique_keep_order(items: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    out = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def pick_new_pmids(
    candidates: Sequence[str],
    needed: int,
    global_seen: Set[str],
    session_seen: Set[str],
    selected_seen: Set[str],
) -> List[str]:
    out = []
    for pmid in candidates:
        if pmid in global_seen or pmid in session_seen or pmid in selected_seen:
            continue
        out.append(pmid)
        selected_seen.add(pmid)
        if len(out) >= needed:
            break
    return out


def classic_query(base_query: str) -> str:
    return f"({base_query}) AND ({CLASSIC_FILTER})"


def collect_articles_for_topic(
    topic: Dict[str, Any],
    fallback_topics: List[Dict[str, Any]],
    args: argparse.Namespace,
    global_seen: Set[str],
    session_seen: Set[str],
) -> List[Article]:
    topic_name = topic["name"]
    query = topic["query"]
    target = int(topic.get("per_topic_count") or args.per_topic_count)
    selected_seen: Set[str] = set()
    articles: List[Article] = []

    def add_stage(stage_query: str, days: int, source_type: str, source_note: str = "") -> None:
        nonlocal articles
        if len(articles) >= target:
            return

        need = target - len(articles)
        print(f"[{topic_name}] {source_type}: searching {days} days, need {need}")
        try:
            pmids = esearch_pubmed(stage_query, days=days, max_results=args.max_results)
        except Exception as exc:
            print(f"[{topic_name}] {source_type} search failed: {exc}", file=sys.stderr)
            return

        picked = pick_new_pmids(pmids, need, global_seen, session_seen, selected_seen)
        if not picked:
            print(f"[{topic_name}] {source_type}: no new PMID")
            return

        try:
            fetched = efetch_pubmed(picked, topic=topic_name, source_type=source_type, source_note=source_note)
        except Exception as exc:
            print(f"[{topic_name}] {source_type} fetch failed: {exc}", file=sys.stderr)
            return

        for article in fetched:
            if article.pmid not in session_seen:
                session_seen.add(article.pmid)
                articles.append(article)

        print(f"[{topic_name}] {source_type}: added {len(fetched)}")
        time.sleep(0.34)

    add_stage(query, args.days, "今日新文献")
    add_stage(query, args.lookback_days, "近期补位")
    add_stage(classic_query(query), args.classic_lookback_days, "经典补位")

    if as_bool(args.enable_fallback_fill) and len(articles) < target:
        for fallback in fallback_topics:
            if len(articles) >= target:
                break
            add_stage(
                fallback["query"],
                args.classic_lookback_days,
                "顶刊扩展",
                source_note=fallback["name"],
            )

    return articles[:target]


def summarize_article(article: Article, use_ai: bool = False, language: str = "zh") -> str:
    if use_ai and os.getenv("OPENAI_API_KEY", ""):
        try:
            return summarize_with_openai(article, language)
        except Exception as exc:
            print(f"OpenAI summary failed for PMID {article.pmid}: {exc}", file=sys.stderr)

    return fallback_summary(article, language)


def summarize_with_openai(article: Article, language: str = "zh") -> str:
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL

    prompt = f"""
请根据下面的 PubMed 文献信息生成中文科研简报总结。

要求：
1. 不要编造摘要中没有的信息。
2. 总字数控制在 120-180 字。
3. 固定使用以下四项：
- 研究目的：
- 研究方法：
- 主要结果：
- 对本课题的启发：

主题分组：{article.topic}
来源类型：{article.source_type}
标题：{article.title}
期刊：{article.journal}
发表日期：{article.pub_date}
摘要：
{article.abstract[:4000]}
"""

    try:
        response = client.responses.create(
            model=model,
            input=prompt,
            temperature=0.2,
        )
        text = getattr(response, "output_text", "")
        if text:
            return text.strip()
    except Exception:
        pass

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a precise biomedical literature assistant. Do not fabricate information."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()


def fallback_summary(article: Article, language: str = "zh") -> str:
    abstract = re.sub(r"\s+", " ", article.abstract or "").strip()

    if not abstract:
        return (
            f"- 研究目的：该文献围绕“{article.title}”相关问题展开，属于“{article.topic}”方向的参考文献。\n"
            f"- 研究方法：PubMed 未提供摘要，需阅读全文确认研究类型、样本来源和实验设计。\n"
            f"- 主要结果：当前仅可根据题名、期刊和主题判断其潜在相关性，不能替代全文解读。\n"
            f"- 对本课题的启发：可作为“{article.topic}”方向的候选文献，建议优先阅读全文判断是否纳入后续综述或课题设计。"
        )

    first_sentences = split_sentences(abstract)
    key_text = " ".join(first_sentences[:3])[:650]

    method_hint = infer_method_hint(article.title + " " + abstract)
    result_hint = key_text

    return (
        f"- 研究目的：该研究聚焦于“{article.title}”所涉及的问题，和“{article.topic}”方向相关。\n"
        f"- 研究方法：从摘要判断，研究可能采用{method_hint}；具体模型、样本量和分析流程需结合全文确认。\n"
        f"- 主要结果：{result_hint}\n"
        f"- 对本课题的启发：该文献可帮助补充“{article.topic}”方向的背景、机制或方法学依据，适合进一步阅读全文筛选。"
    )


def split_sentences(text: str) -> List[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?。！？])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def infer_method_hint(text: str) -> str:
    lower = text.lower()

    if any(x in lower for x in ["single-cell", "single cell", "scrna", "rna-seq", "transcriptom", "proteom", "metabolom", "genom"]):
        return "组学测序或生物信息学分析"
    if any(x in lower for x in ["clinical trial", "randomized", "cohort", "case-control", "retrospective", "prospective"]):
        return "临床研究或队列分析"
    if any(x in lower for x in ["mouse", "mice", "murine", "rat", "animal model"]):
        return "动物模型实验"
    if any(x in lower for x in ["cell", "endothelial", "macrophage", "microglia", "in vitro"]):
        return "细胞实验或体外机制研究"
    if any(x in lower for x in ["mri", "qsm", "radiomics", "imaging", "machine learning"]):
        return "影像学、机器学习或风险预测分析"
    if any(x in lower for x in ["review", "meta-analysis", "systematic review", "guideline"]):
        return "综述、系统评价或指南类文献"
    return "实验、临床或文献分析方法"


def topic_overview(topic_name: str, articles: List[Article]) -> str:
    if not articles:
        return "本组今日未检索到未重复文献。"

    counts = Counter(a.source_type for a in articles)
    journals = [a.journal for a in articles if a.journal and a.journal != "[No journal]"]
    common_journals = ", ".join([x for x, _ in Counter(journals).most_common(3)])

    return (
        f"本组今日共推送 {len(articles)} 篇未重复文献。"
        f"来源构成：今日新文献 {counts.get('今日新文献', 0)} 篇，"
        f"近期补位 {counts.get('近期补位', 0)} 篇，"
        f"经典补位 {counts.get('经典补位', 0)} 篇，"
        f"顶刊扩展 {counts.get('顶刊扩展', 0)} 篇。"
        f"{'主要来源期刊包括：' + common_journals + '。' if common_journals else ''}"
        f"建议优先阅读【今日新文献】和【经典补位】中的综述、临床或机制研究。"
    )


def build_email_body(grouped: Dict[str, List[Article]]) -> str:
    today = today_utc().strftime("%Y-%m-%d")
    total = sum(len(v) for v in grouped.values())

    lines: List[str] = []
    lines.append(f"PubMed每日分组文献汇报 | {today}")
    lines.append("=" * 72)
    lines.append("")
    lines.append(f"今日共推送未重复文献：{total} 篇")
    lines.append("说明：系统会跳过 data/seen_pmids.json 中已经推送过的 PMID。")
    lines.append("来源类型说明：【今日新文献】近3天；【近期补位】近180天；【经典补位】近10年综述/临床/指南；【顶刊扩展】Cell/Nature/Science 等方向扩展。")
    lines.append("")

    chinese_nums = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二", "十三", "十四", "十五"]

    for idx, (topic_name, articles) in enumerate(grouped.items(), start=1):
        num = chinese_nums[idx - 1] if idx <= len(chinese_nums) else str(idx)
        lines.append("")
        lines.append(f"{num}、{topic_name}")
        lines.append("-" * 72)

        if not articles:
            lines.append("本组今日未检索到未重复文献。")
            continue

        if len(articles) < 10:
            lines.append(f"本组今日可用未重复文献不足 10 篇，实际推送 {len(articles)} 篇。")

        lines.append("")
        lines.append("【本组今日概览】")
        lines.append(topic_overview(topic_name, articles))
        lines.append("")

        for i, article in enumerate(articles, start=1):
            source_label = f"【{article.source_type}】"
            if article.source_note:
                source_label += f"({article.source_note})"

            lines.append(f"{i}. {source_label} {article.title}")
            lines.append(f"   PMID: {article.pmid}")
            if article.doi:
                lines.append(f"   DOI: {article.doi}")
            lines.append(f"   期刊: {article.journal}")
            if article.pub_date:
                lines.append(f"   发表日期: {article.pub_date}")
            if article.authors:
                lines.append(f"   作者: {article.authors}")
            lines.append(f"   PubMed: {article.url}")
            lines.append("")
            lines.append("   中文总结：")
            summary = article.summary or fallback_summary(article, "zh")
            for summary_line in summary.splitlines():
                lines.append(f"   {summary_line}")
            lines.append("")

    lines.append("")
    lines.append("=" * 72)
    lines.append("本邮件由 GitHub Actions + PubMed E-utilities 自动生成。")
    return "\n".join(lines)


def send_email(subject: str, body: str) -> None:
    smtp_host = require_env("SMTP_HOST")
    smtp_port = int(require_env("SMTP_PORT"))
    smtp_user = require_env("SMTP_USER")
    smtp_password = require_env("SMTP_PASSWORD")
    smtp_from = require_env("SMTP_FROM")
    smtp_to = require_env("SMTP_TO")

    recipients = [x.strip() for x in smtp_to.split(",") if x.strip()]
    if not recipients:
        raise RuntimeError("SMTP_TO is empty")

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = ", ".join(recipients)
    msg["Date"] = formatdate(localtime=True)

    if smtp_port == 465:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=80) as server:
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, recipients, msg.as_string())
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=80) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, recipients, msg.as_string())


def main() -> int:
    args = parse_args()
    topics, fallback_topics = load_config(args.query_config)
    seen_data = load_seen(args.dedupe_file)

    global_seen = set(str(x) for x in seen_data.get("global_seen_pmids", []))
    session_seen: Set[str] = set()
    grouped: Dict[str, List[Article]] = {}

    print(f"Loaded {len(topics)} topics and {len(fallback_topics)} fallback topics.")
    print(f"Already seen PMIDs: {len(global_seen)}")

    for topic in topics:
        topic_name = topic["name"]
        try:
            articles = collect_articles_for_topic(
                topic=topic,
                fallback_topics=fallback_topics,
                args=args,
                global_seen=global_seen,
                session_seen=session_seen,
            )
        except Exception as exc:
            print(f"Failed to collect topic {topic_name}: {exc}", file=sys.stderr)
            articles = []

        ai_limit = max(0, int(args.ai_summarize_per_topic))
        ai_used = 0

        for idx, article in enumerate(articles):
            use_ai = idx < ai_limit
            if use_ai:
                ai_used += 1
            article.summary = summarize_article(article, use_ai=use_ai, language=args.summary_language)

        print(f"[{topic_name}] final articles: {len(articles)}, AI summaries: {ai_used}")
        grouped[topic_name] = articles

    today = today_utc().strftime("%Y-%m-%d")
    subject = f"PubMed每日分组文献汇报 | {today}"
    body = build_email_body(grouped)

    if args.push == "smtp":
        print("Sending email via SMTP...")
        send_email(subject, body)
        print("Email sent.")
    else:
        print(body)

    new_pmids: List[str] = []
    by_topic = seen_data.setdefault("by_topic", {})

    for topic_name, articles in grouped.items():
        by_topic.setdefault(topic_name, [])
        for article in articles:
            new_pmids.append(article.pmid)
            by_topic[topic_name].append(article.pmid)

    seen_data["global_seen_pmids"] = list(
        OrderedDict.fromkeys(list(seen_data.get("global_seen_pmids", [])) + new_pmids)
    )

    save_seen(args.dedupe_file, seen_data)
    print(f"Updated dedupe file: {args.dedupe_file}")
    print(f"New PMIDs added: {len(new_pmids)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
