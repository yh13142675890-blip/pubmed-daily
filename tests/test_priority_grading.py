import json
import unittest
from pathlib import Path

from priority_grading import classify_literature, grade_priority


FIXTURES = Path(__file__).parent / "fixtures" / "literature_classification.json"


class PriorityGradingTests(unittest.TestCase):
    def test_real_world_regression_fixtures(self) -> None:
        cases = json.loads(FIXTURES.read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(case=case["name"]):
                result = classify_literature(
                    case["title"],
                    case["abstract"],
                    case["topic"],
                )
                self.assertEqual(result["domain"], case["domain"])
                self.assertEqual(result["translational_relevance"], case["relevance"])
                self.assertEqual(result["priority"], case["priority"])

    def test_standalone_ccm_and_cm_are_not_disease_evidence(self) -> None:
        for title in (
            "CCM imaging study",
            "CM clinical trial",
            "Corneal confocal microscopy (CCM)",
            "Cirrhotic cardiomyopathy (CCM)",
        ):
            with self.subTest(title=title):
                result = classify_literature(title, topic="CM影像/QSM/出血风险")
                self.assertNotEqual(result["domain"], "CCM")
                self.assertNotEqual(result["priority"], "S")

    def test_spinal_cavernous_malformation_is_ccm_direct(self) -> None:
        for expression in (
            "spinal cavernous malformation",
            "spinal cord cavernous malformation",
            "spinal cavernoma",
            "intramedullary cavernous malformation",
            "intramedullary cavernoma",
        ):
            with self.subTest(expression=expression):
                result = classify_literature(f"Natural history of {expression}")
                self.assertEqual(result["domain"], "CCM")
                self.assertEqual(result["translational_relevance"], "Direct")

    def test_orbital_and_portal_cavernoma_are_not_ccm(self) -> None:
        for expression in ("orbital cavernoma", "portal cavernoma", "cavernoma"):
            with self.subTest(expression=expression):
                result = classify_literature(f"Clinical imaging of {expression}")
                self.assertNotEqual(result["domain"], "CCM")
                self.assertNotEqual(result["translational_relevance"], "Direct")

    def test_all_qsm_expressions_require_and_upgrade_strong_ccm(self) -> None:
        expressions = (
            "QSM",
            "quantitative susceptibility mapping",
            "quantitative susceptibility",
            "magnetic susceptibility",
            "susceptibility mapping",
            "delta QSM",
            "ΔQSM",
            "QSM change",
            "longitudinal QSM",
        )
        for expression in expressions:
            with self.subTest(expression=expression):
                result = classify_literature(
                    f"{expression} in cerebral cavernous malformations",
                    "A retrospective imaging cohort.",
                )
                self.assertEqual(result["domain"], "CCM")
                self.assertEqual(result["translational_relevance"], "Direct")
                self.assertEqual(result["priority"], "S")

    def test_ccm_trial_terms_are_s(self) -> None:
        terms = (
            "randomized trial",
            "clinical trial",
            "phase II",
            "placebo-controlled",
            "trial readiness",
            "AT CASH EPOC",
            "CARE trial",
            "REC-994 trial",
            "sirolimus trial",
            "everolimus trial",
        )
        for term in terms:
            with self.subTest(term=term):
                result = classify_literature(
                    f"{term} for cerebral cavernous malformations"
                )
                self.assertEqual(result["priority"], "S")

    def test_topic_never_creates_s(self) -> None:
        priority, _ = grade_priority(
            title="Randomized clinical trial in ordinary heart failure",
            topic="CM经典文献/综述补位",
        )
        self.assertEqual(priority, "C")

    def test_pure_immune_assay_terms_do_not_trigger_a(self) -> None:
        for technique in (
            "immunohistochemistry",
            "immunostaining",
            "immunofluorescence",
        ):
            with self.subTest(technique=technique):
                result = classify_literature(
                    "Pediatric postcricoid lesion",
                    f"The sample was analyzed using {technique}.",
                    "神经免疫/炎症治疗",
                )
                self.assertEqual(result["priority"], "C")

    def test_precise_immune_biology_is_a_in_ccm(self) -> None:
        concepts = (
            "immune response",
            "immune cell",
            "immunity",
            "immunology",
            "immunological signaling",
            "immune-mediated inflammation",
            "immunomodulatory treatment",
            "immunosuppressive treatment",
        )
        for concept in concepts:
            with self.subTest(concept=concept):
                result = classify_literature(
                    f"{concept} in cerebral cavernous malformations"
                )
                self.assertEqual(result["priority"], "A")

    def test_drug_name_alone_is_not_a(self) -> None:
        for drug in ("everolimus", "sirolimus", "alpelisib", "aspirin", "fasudil"):
            with self.subTest(drug=drug):
                result = classify_literature(f"{drug} in breast cancer")
                self.assertEqual(result["domain"], "Out-of-scope")
                self.assertEqual(result["priority"], "C")

    def test_drug_with_ccm_or_related_malformation_is_a(self) -> None:
        ccm = classify_literature("Fasudil in cerebral cavernous malformations")
        venous = classify_literature("Sirolimus for venous malformation")
        self.assertEqual(ccm["priority"], "A")
        self.assertEqual(venous["priority"], "A")

    def test_tek_tie2_with_malformation_context_is_venous_domain(self) -> None:
        for gene in ("TEK", "TIE2"):
            with self.subTest(gene=gene):
                result = classify_literature(
                    f"{gene} mutations in vascular malformation",
                    "Somatic endothelial signaling was investigated.",
                )
                self.assertEqual(result["domain"], "Venous malformation")
                self.assertEqual(result["translational_relevance"], "Strong")
                self.assertEqual(result["priority"], "A")

    def test_clinical_terms_are_b_only_in_supported_domains(self) -> None:
        for term in ("natural history", "cohort", "follow-up", "mRS", "radiosurgery", "radiomics"):
            with self.subTest(term=term):
                ccm = classify_literature(f"{term} in cerebral cavernous malformations")
                unrelated = classify_literature(f"{term} in heart failure")
                self.assertEqual(ccm["priority"], "B")
                self.assertEqual(unrelated["priority"], "C")

    def test_plasma_exchange_is_independent_a_interest(self) -> None:
        for term in ("therapeutic plasma exchange", "plasmapheresis", "immunoadsorption", "red cell exchange"):
            with self.subTest(term=term):
                result = classify_literature(term)
                self.assertEqual(result["priority"], "A")
                self.assertEqual(result["special_interest"], "Plasma exchange / blood exchange")
                self.assertEqual(result["translational_relevance"], "Exploratory")
                self.assertIn("Independent", result["translational_reason"])

    def test_cross_domain_requires_mechanism_and_vascular_context(self) -> None:
        result = classify_literature(
            "HIF-dependent endothelial permeability in retinal vascular disease",
            "Hypoxia altered endothelial junctions and vascular permeability.",
        )
        self.assertEqual(result["domain"], "Cross-domain vascular biology")
        self.assertEqual(result["translational_relevance"], "Moderate")
        self.assertEqual(result["priority"], "A")

    def test_generic_cancer_signaling_is_not_cross_domain_a(self) -> None:
        result = classify_literature(
            "PI3K and HIF signaling in colorectal cancer",
            "Tumor metabolism and proliferation were measured.",
        )
        self.assertEqual(result["domain"], "Out-of-scope")
        self.assertEqual(result["priority"], "C")

    def test_vascular_invasion_is_not_sufficient_cross_domain_context(self) -> None:
        result = classify_literature(
            "PI3K signaling and vascular invasion in colorectal cancer",
            "The study assessed tumor growth, metastasis, and treatment resistance.",
        )
        self.assertEqual(result["domain"], "Out-of-scope")
        self.assertEqual(result["translational_relevance"], "Low")
        self.assertEqual(result["priority"], "C")


if __name__ == "__main__":
    unittest.main()
