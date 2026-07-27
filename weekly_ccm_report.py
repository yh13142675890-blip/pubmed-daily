#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple
from zoneinfo import ZoneInfo

from priority_grading import PRIORITY_ORDER, classify_literature
from reporting import build_structured_markdown


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a deterministic weekly CCM literature report")
    parser.add_argument("--daily-reports-dir", default="reports/daily")
    parser.add_argument("--weekly-reports-dir", default="reports/weekly")
    parser.add_argument(
        "--end-date",
        help=(
            "Exclusive end date in YYYY-MM-DD format; defaults to the current week's "
            "Monday in Asia/Shanghai so the previous complete week is reported"
        ),
    )
    return parser.parse_args()


def today_shanghai() -> dt.date:
    return dt.datetime.now(tz=SHANGHAI_TZ).date()


def today_utc() -> dt.date:
    """Backward-compatible alias; weekly periods use Asia/Shanghai."""
    return today_shanghai()


def parse_end_date(value: str | None) -> dt.date:
    return dt.date.fromisoformat(value) if value else previous_complete_week_end(today_shanghai())


def previous_complete_week_end(reference_date: dt.date) -> dt.date:
    return reference_date - dt.timedelta(days=reference_date.weekday())


def report_period(end_date: dt.date) -> Tuple[dt.date, dt.date, str]:
    period_start = end_date - dt.timedelta(days=7)
    period_end = end_date - dt.timedelta(days=1)
    iso_year, iso_week, _ = period_end.isocalendar()
    return period_start, period_end, f"{iso_year}-W{iso_week:02d}"


def daily_report_paths(
    daily_reports_dir: str,
    period_start: dt.date,
    end_date: dt.date,
) -> List[Path]:
    paths: List[Path] = []
    for path in sorted(Path(daily_reports_dir).glob("*.json")):
        try:
            report_date = dt.date.fromisoformat(path.stem)
        except ValueError:
            continue
        if period_start <= report_date < end_date:
            paths.append(path)
    return paths


def load_daily_articles(paths: Sequence[Path]) -> List[Dict[str, Any]]:
    articles: List[Dict[str, Any]] = []
    seen_pmids = set()

    for path in paths:
        try:
            with path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Skipping unreadable daily report {path}: {exc}", file=sys.stderr)
            continue

        raw_articles = payload.get("articles", []) if isinstance(payload, dict) else payload
        if not isinstance(raw_articles, list):
            print(f"Skipping daily report with invalid articles list: {path}", file=sys.stderr)
            continue

        for raw_article in raw_articles:
            if not isinstance(raw_article, dict):
                continue
            pmid = str(raw_article.get("pmid", "")).strip()
            if not pmid or pmid in seen_pmids:
                continue

            article = dict(raw_article)
            classification = classify_literature(
                title=str(article.get("title", "")),
                abstract=str(article.get("abstract", "")),
                topic=str(article.get("topic", "")),
                journal=str(article.get("journal", "")),
            )
            article["pmid"] = pmid
            article.setdefault("source_note", "")
            article.update(classification)
            article["daily_report_date"] = path.stem

            seen_pmids.add(pmid)
            articles.append(article)

    return articles


def build_weekly_payload(
    daily_reports_dir: str,
    end_date: dt.date,
) -> Dict[str, Any]:
    period_start, period_end, week_id = report_period(end_date)
    paths = daily_report_paths(daily_reports_dir, period_start, end_date)
    articles = load_daily_articles(paths)
    grouped = {
        priority: [article for article in articles if article["priority"] == priority]
        for priority in PRIORITY_ORDER
    }

    return {
        "week": week_id,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "timezone": "Asia/Shanghai",
        "source_files": [path.name for path in paths],
        "total_count": len(articles),
        "counts": {priority: len(grouped[priority]) for priority in PRIORITY_ORDER},
        "articles": grouped,
    }


def build_weekly_markdown(payload: Dict[str, Any]) -> str:
    records = [
        article
        for priority in PRIORITY_ORDER
        for article in payload["articles"][priority]
    ]
    return build_structured_markdown(
        title=f"CCM 文献情报周报 | {payload['week']}",
        period_line=(
            f"统计区间：{payload['period_start']} 至 {payload['period_end']}"
            "（Asia/Shanghai，上一个完整自然周）"
        ),
        records=records,
        empty_text="本周无新增文献。",
    )


def write_weekly_reports(
    daily_reports_dir: str = "reports/daily",
    weekly_reports_dir: str = "reports/weekly",
    end_date: dt.date | None = None,
) -> Tuple[Path, Path]:
    effective_end_date = end_date or previous_complete_week_end(today_shanghai())
    payload = build_weekly_payload(daily_reports_dir, effective_end_date)
    output_dir = Path(weekly_reports_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / f"{payload['week']}.json"
    markdown_path = output_dir / f"{payload['week']}.md"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    with markdown_path.open("w", encoding="utf-8") as f:
        f.write(build_weekly_markdown(payload))

    return json_path, markdown_path


def main() -> int:
    args = parse_args()
    json_path, markdown_path = write_weekly_reports(
        daily_reports_dir=args.daily_reports_dir,
        weekly_reports_dir=args.weekly_reports_dir,
        end_date=parse_end_date(args.end_date),
    )
    print(f"Saved weekly JSON report: {json_path}")
    print(f"Saved weekly Markdown report: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
