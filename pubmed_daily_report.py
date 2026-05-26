#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PubMed grouped daily report.

功能：
1. 从 pubmed_topics.yml 读取多个主题检索式；
2. 每组检索 PubMed；
3. 按 seen_pmids.json 去重，尽量保证每天不同；
4. 每组最多推送 N 篇；
5. 每篇文献生成中文总结；
6. 通过 SMTP 发送邮件；
7. 发送成功后更新 seen_pmids.json。
"""

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
from dataclasses import dataclass
from email.mime.text import MIMEText
from email.utils import formatdate
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

import requests
import yaml


EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


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
    summary: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PubMed grouped daily report")

    parser.add_argument("--query-config", default="pubmed_topics.yml")
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--lookback-days", type=int, default=60)
    parser.add_argument("--per-topic-count", type=int, default=10)
    parser.add_argument("--target-count", type=int, default=None)
    parser.add_argument("--max-results", type=int, default=500)
    parser.add_argument("--dedupe-file", default="data/seen_pmids.json")
    parser.add_argument("--summary-language", default="zh", choices=["zh", "en"])
    parser.add_argument("--push", default="smtp", choices=["smtp", "none"])

    return parser.parse_args()


def require_env(name: str, allow_empty: bool = False) -> str:
    value = os.getenv(name, "")
    if not allow_empty and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def today_utc() -> dt.date:
    return dt.datetime.utcnow().date()


def date_range(days: int) -> tuple[str, str]:
    end = today_utc()
    start = end - dt.timedelta(days=max(days - 1, 0))
    return start.strftime("%Y/%m/%d"), end.strftime("%Y/%m/%d")


def load_topics(path: str) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Topic config not found: {path}")

    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    topics = data.get("topics", [])
    if not topics:
        raise ValueError("No topics found in pubmed_topics.yml")

    cleaned = []
    for topic in topics:
        name = str(topic.get("name", "")).strip()
        query = str(topic.get("query", "")).strip()
        per_topic_count = int(topic.get("per_topic_count", 10))
        if not name or not query:
            continue
        cleaned.append(
            {
                "name": name,
                "query": query,
                "per_topic_count": per_topic_count,
            }
        )

    if not cleaned:
        raise ValueError("No valid topics found in pubmed_topics.yml")

    return cleaned


def load_seen(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {
            "global_seen_pmids": [],
            "by_topic": {},
            "updated_at": None,
        }

    with p.open("r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return {
                "global_seen_pmids": [],
                "by_topic": {},
                "updated_at": None,
            }

    data.setdefault("global_seen_pmids", [])
    data.setdefault("by_topic", {})
    data.setdefault("updated_at", None)
    return data


def save_seen(path: str, data: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"

    # 限制文件无限增长。保留最近约 20000 个 PMID，足够长期去重。
    global_seen = list(dict.fromkeys(data.get("global_seen_pmids", [])))
    if len(global_seen) > 20000:
        global_seen = global_seen[-20000:]
    data["global_seen_pmids"] = global_seen

    by_topic = data.get("by_topic", {})
    for topic_name, pmids in by_topic.items():
        pmids = list(dict.fromkeys(pmids))
        if len(pmids) > 5000:
            pmids = pmids[-5000:]
        by_topic[topic_name] = pmids
    data["by_topic"] = by_topic

    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def ncbi_common_params() -> Dict[str, str]:
    params = {}

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

    url = f"{EUTILS_BASE}/esearch.fcgi"
    response = requests.get(url, params=params, timeout=40)
    response.raise_for_status()
    data = response.json()

    ids = data.get("esearchresult", {}).get("idlist", [])
    return [str(x) for x in ids]


def efetch_pubmed(pmids: Sequence[str], topic: str) -> List[Article]:
    if not pmids:
        return []

    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
    }
    params.update(ncbi_common_params())

    url = f"{EUTILS_BASE}/efetch.fcgi"
    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()

    root = ET.fromstring(response.text)
    articles: List[Article] = []

    for pubmed_article in root.findall(".//PubmedArticle"):
        article = parse_pubmed_article(pubmed_article, topic)
        if article:
            articles.append(article)

    return articles


def get_text(elem: Optional[ET.Element]) -> str:
    if elem is None:
        return ""
    text = "".join(elem.itertext())
    text = re.sub(r"\s+", " ", text).strip()
    return html.unescape(text)


def parse_pubmed_article(pubmed_article: ET.Element, topic: str) -> Optional[Article]:
    pmid = get_text(pubmed_article.find(".//PMID"))
    if not pmid:
        return None

    title = get_text(pubmed_article.find(".//ArticleTitle"))
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

    pub_date = parse_pub_date(pubmed_article)
    authors = parse_authors(pubmed_article)
    doi = parse_doi(pubmed_article)

    return Article(
        pmid=pmid,
        title=title or "[No title]",
        abstract=abstract,
        authors=authors,
        journal=journal or "[No journal]",
        pub_date=pub_date,
        doi=doi,
        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        topic=topic,
    )


def parse_authors(pubmed_article: ET.Element, limit: int = 6) -> str:
    author_elems = pubmed_article.findall(".//AuthorList/Author")
    names = []

    for author in author_elems:
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

    if len(names) > limit:
        return ", ".join(names[:limit]) + ", et al."
    return ", ".join(names)


def parse_pub_date(pubmed_article: ET.Element) -> str:
    pub_date = pubmed_article.find(".//JournalIssue/PubDate")
    if pub_date is None:
        return ""

    year = get_text(pub_date.find("Year"))
    month = get_text(pub_date.find("Month"))
    day = get_text(pub_date.find("Day"))
    medline = get_text(pub_date.find("MedlineDate"))

    parts = [x for x in [year, month, day] if x]
    if parts:
        return " ".join(parts)
    return medline


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


def collect_articles_for_topic(
    topic_name: str,
    query: str,
    per_topic_count: int,
    args: argparse.Namespace,
    global_seen: Set[str],
    session_seen: Set[str],
) -> List[Article]:
    print(f"\n[Topic] {topic_name}")

    recent_pmids = esearch_pubmed(query, args.days, args.max_results)
    print(f"  Recent candidates within {args.days} days: {len(recent_pmids)}")

    candidate_pmids = recent_pmids

    if len(candidate_pmids) < per_topic_count * 3:
        lookback_pmids = esearch_pubmed(query, args.lookback_days, args.max_results)
        print(f"  Lookback candidates within {args.lookback_days} days: {len(lookback_pmids)}")
        candidate_pmids = unique_keep_order(candidate_pmids + lookback_pmids)

    candidate_pmids = [
        pmid
        for pmid in candidate_pmids
        if pmid not in global_seen and pmid not in session_seen
    ]

    print(f"  New candidates after dedupe: {len(candidate_pmids)}")

    selected_pmids = candidate_pmids[:per_topic_count]
    if not selected_pmids:
        return []

    articles = efetch_pubmed(selected_pmids, topic_name)

    # 保持 PMID 顺序
    article_map = {a.pmid: a for a in articles}
    ordered = [article_map[pmid] for pmid in selected_pmids if pmid in article_map]

    for article in ordered:
        session_seen.add(article.pmid)

    time.sleep(0.34)
    return ordered


def summarize_article(article: Article, language: str = "zh") -> str:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key:
        try:
            return summarize_with_openai(article, language)
        except Exception as exc:
            print(f"  OpenAI summary failed for PMID {article.pmid}: {exc}", file=sys.stderr)

    return fallback_summary(article, language)


def summarize_with_openai(article: Article, language: str = "zh") -> str:
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL

    if language == "zh":
        prompt = f"""
请根据下面的 PubMed 文献信息生成中文科研简报总结。

要求：
1. 总字数控制在 120-180 字。
2. 不要夸大，不要编造摘要中没有的信息。
3. 固定使用以下四项：
- 研究目的：
- 研究方法：
- 主要结果：
- 对本课题的启发：

主题分组：{article.topic}
标题：{article.title}
期刊：{article.journal}
发表日期：{article.pub_date}
摘要：
{article.abstract[:4000]}
"""
    else:
        prompt = f"""
Summarize this PubMed article in 120-180 words.
Use four fields: Objective, Methods, Key findings, Relevance.

Topic: {article.topic}
Title: {article.title}
Journal: {article.journal}
Date: {article.pub_date}
Abstract:
{article.abstract[:4000]}
"""

    # 优先使用 Responses API；失败时自动回退到 Chat Completions。
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
            {
                "role": "system",
                "content": "You are a precise biomedical literature assistant. Do not fabricate information.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()


def fallback_summary(article: Article, language: str = "zh") -> str:
    abstract = re.sub(r"\s+", " ", article.abstract or "").strip()
    if not abstract:
        abstract = "该文献未提供摘要，建议根据全文进一步判断研究设计、主要结果及其与当前课题的关系。"

    short_abs = abstract[:450]
    if language == "zh":
        return (
            f"- 研究目的：围绕“{article.title}”相关问题展开。\n"
            f"- 研究方法：根据题名和摘要信息判断，研究主要基于文献所述实验、临床或数据分析方法。\n"
            f"- 主要结果：{short_abs}\n"
            f"- 对本课题的启发：可作为“{article.topic}”方向的候选参考文献，建议阅读全文确认模型、样本和结论强度。"
        )

    return (
        f"- Objective: This article addresses the topic reflected in the title: {article.title}.\n"
        f"- Methods: The detailed design should be confirmed from the full text.\n"
        f"- Key findings: {short_abs}\n"
        f"- Relevance: Potentially relevant to the topic group: {article.topic}."
    )


def summarize_topic_overview(topic_name: str, articles: List[Article]) -> str:
    if not articles:
        return "本组今日未检索到未重复的新文献。"

    titles = "；".join([a.title for a in articles[:10]])
    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
            model = os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
            prompt = f"""
请对以下 PubMed 文献标题进行一个中文“本组今日概览”。
要求：
1. 80-120 字。
2. 总结共同趋势、值得关注的研究方向。
3. 不要编造标题之外的信息。

主题：{topic_name}
标题列表：
{titles}
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
                    {"role": "system", "content": "You summarize biomedical literature trends accurately."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            print(f"  Topic overview failed for {topic_name}: {exc}", file=sys.stderr)

    return f"本组今日共筛选到 {len(articles)} 篇未重复文献，主题集中于 {topic_name} 相关方向，建议优先阅读标题和摘要与当前课题最贴近的文章。"


def build_email_body(grouped: Dict[str, List[Article]]) -> str:
    today = today_utc().strftime("%Y-%m-%d")
    total = sum(len(v) for v in grouped.values())

    lines: List[str] = []
    lines.append(f"PubMed每日分组文献汇报 | {today}")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"今日共推送未重复文献：{total} 篇")
    lines.append("说明：系统已根据 seen_pmids.json 自动跳过历史已推送 PMID。")
    lines.append("")

    chinese_nums = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]

    for idx, (topic_name, articles) in enumerate(grouped.items(), start=1):
        num = chinese_nums[idx - 1] if idx <= len(chinese_nums) else str(idx)
        lines.append("")
        lines.append(f"{num}、{topic_name}")
        lines.append("-" * 60)

        if not articles:
            lines.append("本组今日未检索到未重复的新文献。")
            continue

        if len(articles) < 10:
            lines.append(f"本组今日未重复文献不足 10 篇，实际推送 {len(articles)} 篇。")

        lines.append("")
        lines.append("【本组今日概览】")
        lines.append(summarize_topic_overview(topic_name, articles))
        lines.append("")

        for i, article in enumerate(articles, start=1):
            lines.append(f"{i}. {article.title}")
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
            for summary_line in article.summary.splitlines():
                lines.append(f"   {summary_line}")
            lines.append("")

    lines.append("")
    lines.append("=" * 60)
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
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=60) as server:
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, recipients, msg.as_string())
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=60) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, recipients, msg.as_string())


def main() -> int:
    args = parse_args()

    topics = load_topics(args.query_config)
    seen_data = load_seen(args.dedupe_file)

    global_seen = set(str(x) for x in seen_data.get("global_seen_pmids", []))
    session_seen: Set[str] = set()

    grouped: Dict[str, List[Article]] = {}

    for topic in topics:
        topic_name = topic["name"]
        query = topic["query"]
        count = int(topic.get("per_topic_count") or args.per_topic_count or 10)

        try:
            articles = collect_articles_for_topic(
                topic_name=topic_name,
                query=query,
                per_topic_count=count,
                args=args,
                global_seen=global_seen,
                session_seen=session_seen,
            )
        except Exception as exc:
            print(f"Failed to collect topic {topic_name}: {exc}", file=sys.stderr)
            articles = []

        for article in articles:
            print(f"  Summarizing PMID {article.pmid}: {article.title[:80]}")
            article.summary = summarize_article(article, args.summary_language)
            time.sleep(0.2)

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

    # 只有邮件发送成功后才更新去重库。
    new_pmids = []
    by_topic = seen_data.setdefault("by_topic", {})
    for topic_name, articles in grouped.items():
        by_topic.setdefault(topic_name, [])
        for article in articles:
            new_pmids.append(article.pmid)
            by_topic[topic_name].append(article.pmid)

    seen_data["global_seen_pmids"] = list(
        dict.fromkeys(list(seen_data.get("global_seen_pmids", [])) + new_pmids)
    )

    save_seen(args.dedupe_file, seen_data)
    print(f"Updated dedupe file: {args.dedupe_file}")
    print(f"New PMIDs added: {len(new_pmids)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
