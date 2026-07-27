import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from weekly_ccm_report import write_weekly_reports


def make_record(pmid: str, title: str, topic: str = "测试主题") -> dict:
    return {
        "pmid": pmid,
        "title": title,
        "abstract": "Test abstract",
        "journal": "Test Journal",
        "authors": "Author A",
        "publication_date": "2026 Jul",
        "doi": f"10.1000/{pmid}",
        "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "topic": topic,
        "source_type": "今日新文献",
    }


def write_daily_report(directory: Path, report_date: str, articles: list) -> None:
    payload = {"date": report_date, "count": len(articles), "articles": articles}
    (directory / f"{report_date}.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


class WeeklyCcmReportTests(unittest.TestCase):
    def test_weekly_report_reads_previous_seven_complete_days(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            daily_dir = root / "daily"
            weekly_dir = root / "weekly"
            daily_dir.mkdir()

            write_daily_report(daily_dir, "2026-07-19", [make_record("999", "QSM in CCM")])

            s_article = make_record(
                "1001",
                "QSM cohort of hemorrhage in CCM",
                topic="CM影像/QSM/出血风险",
            )
            s_article["priority"] = "B"
            s_article["priority_reason"] = "stale value"
            write_daily_report(daily_dir, "2026-07-20", [s_article])
            write_daily_report(daily_dir, "2026-07-21", [make_record("1002", "Single-cell cohort")])
            write_daily_report(daily_dir, "2026-07-22", [make_record("1003", "Natural history cohort")])
            write_daily_report(daily_dir, "2026-07-23", [make_record("1004", "Broad background review")])
            write_daily_report(daily_dir, "2026-07-24", [make_record("1001", "Duplicate PMID")])
            write_daily_report(daily_dir, "2026-07-27", [make_record("1005", "mTOR study")])

            json_path, markdown_path = write_weekly_reports(
                daily_reports_dir=str(daily_dir),
                weekly_reports_dir=str(weekly_dir),
                end_date=date(2026, 7, 27),
            )

            payload = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")

        self.assertEqual(json_path.name, "2026-W30.json")
        self.assertEqual(markdown_path.name, "2026-W30.md")
        self.assertEqual(payload["period_start"], "2026-07-20")
        self.assertEqual(payload["period_end"], "2026-07-26")
        self.assertEqual(payload["total_count"], 4)
        self.assertEqual(payload["counts"], {"S": 1, "A": 1, "B": 1, "C": 1})
        self.assertEqual(payload["articles"]["S"][0]["priority_reason"], "S: CM/CCM + QSM")
        self.assertNotIn("2026-07-19.json", payload["source_files"])
        self.assertNotIn("2026-07-27.json", payload["source_files"])
        self.assertIn("## S 级文献（1）", markdown)
        self.assertIn("## C 级文献（1）", markdown)

    def test_weekly_report_is_created_without_daily_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            daily_dir = root / "daily"
            weekly_dir = root / "weekly"
            daily_dir.mkdir()

            json_path, markdown_path = write_weekly_reports(
                daily_reports_dir=str(daily_dir),
                weekly_reports_dir=str(weekly_dir),
                end_date=date(2026, 7, 27),
            )

            payload = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")

        self.assertEqual(payload["total_count"], 0)
        self.assertEqual(payload["counts"], {"S": 0, "A": 0, "B": 0, "C": 0})
        self.assertIn("本周无此级别文献", markdown)


if __name__ == "__main__":
    unittest.main()
