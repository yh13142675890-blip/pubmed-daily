import unittest

from priority_grading import grade_priority


class PriorityGradingTests(unittest.TestCase):
    def test_cm_qsm_is_always_s_even_with_b_signals(self) -> None:
        priority, reason = grade_priority(
            title="QSM cohort study of hemorrhage outcomes in CM",
            abstract="Quantitative susceptibility mapping for lesion burden.",
            topic="General imaging",
        )

        self.assertEqual(priority, "S")
        self.assertEqual(reason, "S: CM/CCM + QSM")

    def test_cm_clinical_trial_is_s(self) -> None:
        priority, reason = grade_priority(
            title="Clinical trial readiness framework",
            abstract="A multicenter cohort framework.",
            topic="CM药物治疗",
        )

        self.assertEqual(priority, "S")
        self.assertIn("clinical trial", reason)

    def test_qsm_in_mixed_topic_name_does_not_make_every_article_s(self) -> None:
        priority, reason = grade_priority(
            title="MRI cohort of hemorrhage risk",
            abstract="Clinical imaging outcomes in cavernous malformation.",
            topic="CM影像/QSM/出血风险",
        )

        self.assertEqual(priority, "B")
        self.assertEqual(reason, "B: cohort")

    def test_a_signals_override_b_signals(self) -> None:
        cases = (
            ("Single-cell cohort analysis", "A: single-cell"),
            ("Spatial transcriptomics and outcome", "A: spatial transcriptomics"),
            ("RNA-seq cohort", "A: RNA-seq"),
            ("Proteomics of hemorrhage", "A: proteomics"),
            ("Metabolomics cohort", "A: metabolomics"),
            ("Multi-omics outcome study", "A: multi-omics"),
            ("mTOR imaging study", "A: mTOR/PI3K-AKT"),
            ("HIF-1α and hemorrhage", "A: HIF1A/HIF-1α"),
            ("EPAS1 outcome study", "A: EPAS1/HIF-2α"),
            ("Immune cohort analysis", "A: immune/inflammation/metabolism"),
            ("Therapeutic plasma exchange cohort", "A: plasma exchange / plasmapheresis / blood exchange"),
        )

        for title, expected_reason in cases:
            with self.subTest(title=title):
                priority, reason = grade_priority(title=title)
                self.assertEqual(priority, "A")
                self.assertEqual(reason, expected_reason)

    def test_ccm_basic_mechanism_topic_is_a(self) -> None:
        priority, reason = grade_priority(
            title="Endothelial signaling and surgical outcomes",
            topic="CM基础机制",
        )

        self.assertEqual(priority, "A")
        self.assertEqual(reason, "A: CCM基础机制")

    def test_b_and_c_fallback_rules(self) -> None:
        self.assertEqual(grade_priority(title="Natural history cohort")[0], "B")
        self.assertEqual(grade_priority(title="Epilepsy after surgery")[0], "B")
        self.assertEqual(grade_priority(title="A broad background review")[0], "C")
        self.assertEqual(grade_priority(title="Unclassified publication")[0], "C")


if __name__ == "__main__":
    unittest.main()
