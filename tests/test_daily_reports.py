import json
import datetime as dt
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pubmed_daily_report import (
    Article,
    load_config,
    load_seen,
    main,
    save_seen,
    today_shanghai,
    write_daily_reports,
)


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
    def test_reports_include_all_current_run_source_types_once(self) -> None:
        daily_article = make_article("1001", "今日新文献")
        classic_qsm_article = make_article(
            "1003",
            "经典补位",
            topic="CM影像/QSM/出血风险",
        )
        classic_qsm_article.title = "Magnetic susceptibility in cerebral cavernous malformations"
        grouped = {
            "测试主题": [
                daily_article,
                make_article("1002", "近期补位"),
                classic_qsm_article,
                make_article("1004", "顶刊扩展"),
            ],
            "重复主题": [make_article("1002", "近期补位")],
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
        self.assertEqual(payload["count"], 4)
        self.assertEqual(
            [article["pmid"] for article in payload["articles"]],
            ["1001", "1002", "1003", "1004"],
        )
        self.assertEqual(
            [article["source_type"] for article in payload["articles"]],
            ["今日新文献", "近期补位", "经典补位", "顶刊扩展"],
        )
        required_fields = {
            "pmid",
            "title",
            "abstract",
            "journal",
            "authors",
            "publication_date",
            "doi",
            "pubmed_url",
            "topic",
            "source_type",
            "source_note",
            "special_interest",
            "domain",
            "domain_reason",
            "translational_relevance",
            "translational_reason",
            "priority",
            "priority_reason",
        }
        self.assertTrue(all(required_fields <= article.keys() for article in payload["articles"]))
        classic_record = next(article for article in payload["articles"] if article["pmid"] == "1003")
        self.assertEqual(classic_record["priority"], "S")
        self.assertEqual(classic_record["domain"], "CCM")
        self.assertEqual(classic_record["translational_relevance"], "Direct")
        for pmid in ("1001", "1002", "1003", "1004"):
            expected_title = "Magnetic susceptibility in cerebral cavernous malformations" if pmid == "1003" else f"Title {pmid}"
            self.assertIn(expected_title, markdown)

    def test_reports_are_created_when_there_are_no_daily_articles(self) -> None:
        grouped = {"测试主题": []}

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
                patch("pubmed_daily_report.today_shanghai", return_value=date(2026, 7, 29)),
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
        self.assertEqual(
            [article["pmid"] for article in payload["articles"]],
            ["3001", "3002"],
        )
        self.assertEqual(
            [article["source_type"] for article in payload["articles"]],
            ["今日新文献", "经典补位"],
        )

    def test_same_day_runs_merge_without_overwriting_or_duplicate_pmids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            write_daily_reports(
                {"first": [make_article("A", "今日新文献"), make_article("B", "近期补位")]},
                "2026-07-28",
                reports_dir=temp_dir,
            )
            json_path, markdown_path = write_daily_reports(
                {
                    "second": [
                        make_article("B", "近期补位"),
                        make_article("C", "经典补位"),
                        make_article("D", "顶刊扩展"),
                    ]
                },
                "2026-07-28",
                reports_dir=temp_dir,
            )
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")

        self.assertEqual([article["pmid"] for article in payload["articles"]], ["A", "B", "C", "D"])
        self.assertEqual(payload["count"], 4)
        self.assertEqual(markdown.count("PMID: B"), 1)

    def test_business_date_uses_shanghai_when_utc_is_previous_day(self) -> None:
        real_datetime = dt.datetime

        class FixedDateTime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                instant = real_datetime(2026, 7, 27, 23, 30, tzinfo=dt.timezone.utc)
                return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

        with patch("pubmed_daily_report.dt.datetime", FixedDateTime):
            report_date = today_shanghai()
            with tempfile.TemporaryDirectory() as temp_dir:
                json_path, _ = write_daily_reports(
                    {"测试": []},
                    report_date.isoformat(),
                    reports_dir=temp_dir,
                )
            self.assertEqual(report_date, date(2026, 7, 28))
            self.assertEqual(json_path.name, "2026-07-28.json")

    def test_topic_classic_lookback_days_is_loaded(self) -> None:
        config = """
topics:
  - name: QSM
    query: qsm
    classic_lookback_days: 9000
fallback_topics: []
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "topics.yml"
            path.write_text(config, encoding="utf-8")
            topics, _ = load_config(str(path))
        self.assertEqual(topics[0]["classic_lookback_days"], 9000)

    def test_all_ccm_queries_include_spinal_terms_without_generic_cavernoma(self) -> None:
        config_path = Path(__file__).parents[1] / "pubmed_topics.yml"
        topics, _ = load_config(str(config_path))
        ccm_topics = [topic for topic in topics if topic["name"].startswith("CM")]

        self.assertGreaterEqual(len(ccm_topics), 5)
        for topic in ccm_topics:
            with self.subTest(topic=topic["name"]):
                query = topic["query"]
                self.assertIn('"spinal cord cavernous malformation"', query)
                self.assertIn('"intramedullary cavernoma"', query)
                self.assertNotIn("OR cavernoma[Title/Abstract]", query)
                self.assertNotIn("OR cavernomas[Title/Abstract]", query)

    def test_plasma_exchange_is_special_interest_and_not_repeated_in_low_section(self) -> None:
        plasma = make_article("4001", "今日新文献", topic="换血/血浆置换疗法")
        plasma.title = "Therapeutic plasma exchange for autoimmune disease"

        with tempfile.TemporaryDirectory() as temp_dir:
            json_path, markdown_path = write_daily_reports(
                {"换血/血浆置换疗法": [plasma]},
                "2026-07-30",
                reports_dir=temp_dir,
            )
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")

        record = payload["articles"][0]
        self.assertEqual(record["special_interest"], "Plasma exchange / blood exchange")
        self.assertEqual(record["priority"], "A")
        self.assertEqual(record["translational_relevance"], "Exploratory")
        self.assertEqual(markdown.count(plasma.title), 1)
        self.assertIn("## 4. 血浆置换 / 换血（1）", markdown)
        self.assertIn("## 6. 低相关性 / 范围外记录（0）", markdown)

    def test_screened_fallback_state_persists_separately_from_global_seen(self) -> None:
        data = {
            "global_seen_pmids": ["seen"],
            "screened_out_fallback_pmids": ["screened", "screened"],
            "by_topic": {},
            "updated_at": None,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "seen.json"
            save_seen(str(path), data)
            loaded = load_seen(str(path))

        self.assertEqual(loaded["global_seen_pmids"], ["seen"])
        self.assertEqual(loaded["screened_out_fallback_pmids"], ["screened"])
        self.assertNotIn("screened", loaded["global_seen_pmids"])


if __name__ == "__main__":
    unittest.main()
