import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pubmed_daily_report import (
    Article,
    collect_articles_for_topic,
    collect_cross_domain_articles,
)


def article(pmid: str, title: str, abstract: str = "") -> Article:
    return Article(
        pmid=pmid,
        title=title,
        abstract=abstract,
        authors="Author",
        journal="Nature Medicine",
        pub_date="2026",
        doi="",
        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        topic="跨领域顶刊启发",
        source_type="顶刊扩展",
        source_note="fixture fallback",
    )


class SearchCollectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.args = SimpleNamespace(
            days=3,
            lookback_days=180,
            classic_lookback_days=3650,
            per_topic_count=10,
            max_results=800,
            enable_fallback_fill="true",
        )

    def test_primary_topic_is_not_force_filled_and_uses_topic_lookback(self) -> None:
        topic = {
            "name": "CM影像/QSM/出血风险",
            "query": "strong-ccm-query",
            "per_topic_count": 10,
            "classic_lookback_days": 9000,
        }
        with patch("pubmed_daily_report.esearch_pubmed", return_value=[]) as search:
            result = collect_articles_for_topic(
                topic,
                [{"name": "generic", "query": "generic-fallback"}],
                self.args,
                global_seen=set(),
                session_seen=set(),
            )

        self.assertEqual(result, [])
        self.assertEqual([item.kwargs["days"] for item in search.call_args_list], [3, 180, 9000])
        self.assertTrue(all("generic-fallback" not in item.args[0] for item in search.call_args_list))

    def test_top_journal_articles_use_separate_topic_and_relevance_filter(self) -> None:
        rejected = article(
            "1",
            "PI3K and HIF in colorectal cancer",
            "Tumor metabolism and proliferation.",
        )
        accepted = article(
            "2",
            "HIF-dependent endothelial permeability in retinal vascular disease",
            "Hypoxia disrupted endothelial junctions and vascular permeability.",
        )
        session_seen = set()
        screened_out = set()
        with (
            patch("pubmed_daily_report.esearch_pubmed", return_value=["1", "2"]),
            patch("pubmed_daily_report.efetch_pubmed", return_value=[rejected, accepted]),
            patch("pubmed_daily_report.time.sleep"),
        ):
            result = collect_cross_domain_articles(
                [{"name": "fixture fallback", "query": "top-journal-query"}],
                self.args,
                global_seen=set(),
                session_seen=session_seen,
                screened_out_fallback_pmids=screened_out,
            )

        self.assertEqual([item.pmid for item in result], ["2"])
        self.assertEqual(result[0].topic, "跨领域顶刊启发")
        self.assertEqual(result[0].source_type, "顶刊扩展")
        self.assertEqual(result[0].source_note, "fixture fallback")
        self.assertEqual(session_seen, {"2"})
        self.assertEqual(screened_out, {"1"})

    def test_rejected_fallback_pmid_is_not_fetched_again(self) -> None:
        rejected = article(
            "1",
            "PI3K signaling and vascular invasion in colorectal cancer",
            "Tumor growth and treatment resistance were assessed.",
        )
        screened_out = set()
        with (
            patch("pubmed_daily_report.esearch_pubmed", return_value=["1"]),
            patch("pubmed_daily_report.efetch_pubmed", return_value=[rejected]) as fetch,
            patch("pubmed_daily_report.time.sleep"),
        ):
            first = collect_cross_domain_articles(
                [{"name": "fixture fallback", "query": "top-journal-query"}],
                self.args,
                global_seen=set(),
                session_seen=set(),
                screened_out_fallback_pmids=screened_out,
            )
            second = collect_cross_domain_articles(
                [{"name": "fixture fallback", "query": "top-journal-query"}],
                self.args,
                global_seen=set(),
                session_seen=set(),
                screened_out_fallback_pmids=screened_out,
            )

        self.assertEqual(first, [])
        self.assertEqual(second, [])
        self.assertEqual(screened_out, {"1"})
        self.assertEqual(fetch.call_count, 1)


if __name__ == "__main__":
    unittest.main()
