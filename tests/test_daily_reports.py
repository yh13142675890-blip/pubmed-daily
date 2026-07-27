import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pubmed_daily_report import Article, main, write_daily_reports


def make_article(pmid: str, source_type: str, topic: str = "测试主题") -> Article:
    return Article(
        pmid=pmid,
        title=f"Title {pmid}",
        abstract=f"Abstract {pmid}",
        authors="Author A, Author B",
        journal="Test Journal",
        pub_date="2026 Jul 27",
        doi=f"10.1000/{pmid}",
        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        topic=topic,
        source_type=source_type,
    )


class DailyReportTests(unittest.TestCase):
    def test_reports_include_only_current_daily_articles(self) -> None:
        daily_article = make_article("1001", "今日新文献")
        grouped = {
            "测试主题": [
                daily_article,
                make_article("1002", "近期补位"),
                make_article("1003", "经典补位"),
                make_article("1004", "顶刊扩展"),
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            json_path, markdown_path = write_daily_reports(
                grouped,
                "2026-07-27",
                reports_dir=temp_dir,
            )

            payload = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")

        self.assertEqual(payload["date"], "2026-07-27")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(
            payload["articles"],
            [
                {
                    "pmid": "1001",
                    "title": "Title 1001",
                    "abstract": "Abstract 1001",
                    "journal": "Test Journal",
                    "authors": "Author A, Author B",
                    "publication_date": "2026 Jul 27",
                    "doi": "10.1000/1001",
                    "pubmed_url": "https://pubmed.ncbi.nlm.nih.gov/1001/",
                    "topic": "测试主题",
                    "source_type": "今日新文献",
                    "priority": "C",
                    "priority_reason": "C: no S/A/B priority signal matched",
                }
            ],
        )
        self.assertIn("Title 1001", markdown)
        self.assertNotIn("Title 1002", markdown)
        self.assertNotIn("Title 1003", markdown)
        self.assertNotIn("Title 1004", markdown)

    def test_reports_are_created_when_there_are_no_daily_articles(self) -> None:
        grouped = {"测试主题": [make_article("2001", "近期补位")]}

        with tempfile.TemporaryDirectory() as temp_dir:
            json_path, markdown_path = write_daily_reports(
                grouped,
                "2026-07-28",
                reports_dir=temp_dir,
            )

            payload = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")

        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["articles"], [])
        self.assertIn("未检索到真正新增的文献", markdown)

    def test_main_keeps_email_and_seen_updates_separate_from_daily_report(self) -> None:
        daily_article = make_article("3001", "今日新文献")
        fallback_article = make_article("3002", "经典补位")
        seen_data = {
            "global_seen_pmids": ["existing"],
            "by_topic": {},
            "updated_at": None,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            args = SimpleNamespace(
                query_config="topics.yml",
                dedupe_file="seen.json",
                daily_reports_dir=temp_dir,
                ai_summarize_per_topic=0,
                summary_language="zh",
                push="smtp",
            )
            with (
                patch("pubmed_daily_report.parse_args", return_value=args),
                patch(
                    "pubmed_daily_report.load_config",
                    return_value=([{"name": "测试主题", "query": "query"}], []),
                ),
                patch("pubmed_daily_report.load_seen", return_value=seen_data),
                patch(
                    "pubmed_daily_report.collect_articles_for_topic",
                    return_value=[daily_article, fallback_article],
                ),
                patch("pubmed_daily_report.summarize_article", return_value="summary"),
                patch("pubmed_daily_report.build_email_body", return_value="email body"),
                patch("pubmed_daily_report.send_email") as send_email,
                patch("pubmed_daily_report.save_seen") as save_seen,
                patch("pubmed_daily_report.today_utc", return_value=date(2026, 7, 29)),
            ):
                result = main()

            payload = json.loads(
                (Path(temp_dir) / "2026-07-29.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result, 0)
        send_email.assert_called_once_with(
            "PubMed每日分组文献汇报 | 2026-07-29",
            "email body",
        )
        save_seen.assert_called_once_with("seen.json", seen_data)
        self.assertEqual(
            seen_data["global_seen_pmids"],
            ["existing", "3001", "3002"],
        )
        self.assertEqual(seen_data["by_topic"]["测试主题"], ["3001", "3002"])
        self.assertEqual([article["pmid"] for article in payload["articles"]], ["3001"])


if __name__ == "__main__":
    unittest.main()
