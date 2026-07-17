import importlib.util
import sys
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "build_breeder_affiliations",
    ROOT / "scripts" / "build_breeder_affiliations.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class BreederAffiliationTests(unittest.TestCase):
    def test_repeated_patent_assignee_evidence_is_high_confidence(self):
        counts = Counter({"patent_assignee": 2, "cultivar_match": 3})
        self.assertEqual(MODULE.infer_confidence(counts, 1.0, 0), "high")

    def test_repeated_co_listing_is_probable_when_not_dominant_enough_for_high(self):
        counts = Counter({"co_listed_entity": 2, "cultivar_match": 2})
        self.assertEqual(MODULE.infer_confidence(counts, 0.7, 2), "medium")

    def test_cultivar_match_alone_never_verifies_relationship(self):
        counts = Counter({"cultivar_match": 20})
        self.assertEqual(MODULE.infer_confidence(counts, 0.0, 0), "low")

    def test_verified_relationship_requires_high_identity_confidence(self):
        self.assertEqual(
            MODULE.affiliation_status("high", "medium"),
            "probable_relationship",
        )
        self.assertEqual(
            MODULE.affiliation_status("high", "high"),
            "verified_relationship",
        )


if __name__ == "__main__":
    unittest.main()
