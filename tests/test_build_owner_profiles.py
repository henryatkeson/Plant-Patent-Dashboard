import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_owner_profiles", ROOT / "scripts" / "build_owner_profiles.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class OwnerProfileTests(unittest.TestCase):
    def test_compound_breeder_aliases_preserve_both_people(self):
        names = MODULE.split_people_or_entities(
            "Lowell Glen Bradford (US)/Jon M. QUISENBERRY (US)"
        )
        self.assertEqual(names, ["Lowell Glen Bradford", "Jon M. Quisenberry"])

    def test_bradford_combined_variant_preserves_both_people(self):
        names = MODULE.split_people_or_entities("N.G. & L.G. Bradford")
        self.assertEqual(names, ["Norman Glen Bradford", "Lowell Glen Bradford"])

    def test_ben_dor_company_and_breeder_remain_distinct(self):
        names = MODULE.split_people_or_entities(
            "Ben-Dor Fruits and Nurseries; Yosef Ben-Dor"
        )
        self.assertEqual(names, ["Ben-Dor Fruits and Nurseries", "Yosef Ben-Dor"])
        self.assertEqual(
            MODULE.company_profile_for_name(names[0])["canonicalName"],
            "Ben Dor Fruits & Nurseries Ltd",
        )
        self.assertEqual(
            MODULE.canonical_named_party(names[1], {}),
            "Yossef Ben-Dor",
        )

    def test_legal_entity_ampersand_is_not_split_as_people(self):
        names = MODULE.split_people_or_entities("Ben-Dor Fruits & Nurseries Ltd.")
        self.assertEqual(names, ["Ben-Dor Fruits & Nurseries Ltd."])

    def test_surname_first_bradford_variant_is_canonicalized(self):
        self.assertEqual(
            MODULE.canonical_named_party("Bradford, Norman G.", {}),
            "Norman Glen Bradford",
        )

    def test_israeli_breeder_export_variants_are_canonicalized(self):
        self.assertEqual(
            MODULE.canonical_named_party("Efraim Yosef, Israel", {}),
            "Efraim Yosef",
        )
        self.assertEqual(
            MODULE.canonical_named_party("Asaf Meisles", {}),
            "Asaf Meizles",
        )

    def test_trailing_country_code_location_is_not_a_breeder(self):
        self.assertTrue(MODULE.looks_like_address_or_location("Hod HaSharon, IL"))
        self.assertEqual(MODULE.canonical_named_party("Hod HaSharon, IL", {}), "")

    def test_parent_rollup_deduplicates_shared_record(self):
        record = {
            "id": "TEST-1",
            "sourceKind": "CPVO Plant breeders' rights",
            "registerType": "PBR",
            "country": "US",
            "crop": "Peach",
            "cultivar": "Example One",
            "applicationDate": "2024-01-01",
            "grantDate": "2025-01-01",
            "breeders": "Jane Breeder",
        }
        children = [
            {
                "_recordIds": {"TEST-1"},
                "_recordRoles": {"TEST-1": {"CPVO breeder"}},
            },
            {
                "_recordIds": {"TEST-1"},
                "_recordRoles": {"TEST-1": {"Patent assignee"}},
            },
        ]
        result = MODULE.summarize_rollup_records(
            children,
            {"TEST-1": record},
            {},
        )

        self.assertEqual(result["recordCount"], 1)
        self.assertEqual(result["distinctCultivarCount"], 1)
        self.assertEqual(result["protectedIpCount"], 1)
        self.assertEqual(result["legalOwnerRecordCount"], 1)
        self.assertEqual(result["breederSignalRecordCount"], 1)
        self.assertEqual(result["ownerRoleCounts"]["Patent assignee"], 1)
        self.assertEqual(result["ownerRoleCounts"]["CPVO breeder"], 1)

    def test_unresolved_identity_is_suppressed_from_target_ranking(self):
        score, band, _reasons, blockers = MODULE.score_acquisition_fit(
            {
                "recordCount": 25,
                "protectedIpCount": 20,
                "relevantIpRecordCount": 25,
                "activeProtectionCount": 20,
                "recordsLast5Years": 8,
                "cropConcentration": 1.0,
                "individualOwner": True,
                "webResearchStatus": "unresolved",
                "ownershipType": "identity unresolved",
            }
        )

        self.assertLessEqual(score, 25)
        self.assertEqual(band, "Identity unresolved")
        self.assertIn("Identity cannot be matched to a unique breeder or owner", blockers)

    def test_strategic_scale_profile_is_capped_as_too_large(self):
        score, band, _reasons, blockers = MODULE.score_acquisition_fit(
            {
                "recordCount": 30,
                "protectedIpCount": 25,
                "relevantIpRecordCount": 30,
                "activeProtectionCount": 25,
                "recordsLast5Years": 10,
                "cropConcentration": 1.0,
                "companyWebsite": "https://example.com",
                "acquisitionScaleClass": "strategic_scale",
            }
        )

        self.assertLessEqual(score, 30)
        self.assertEqual(band, "Benchmark / too large")
        self.assertIn("Benchmark-scale or institutionally owned platform", blockers)

    def test_unresearched_breeder_only_profile_cannot_rank_as_verified_succession_lead(self):
        score, band, _reasons, _blockers = MODULE.score_acquisition_fit(
            {
                "recordCount": 25,
                "protectedIpCount": 20,
                "relevantIpRecordCount": 25,
                "activeProtectionCount": 20,
                "recordsLast5Years": 8,
                "cropConcentration": 1.0,
                "individualOwner": True,
                "legalOwnerRecordCount": 0,
            }
        )

        self.assertLessEqual(score, 50)
        self.assertEqual(band, "Affiliation research needed")

    def test_every_suppressed_profile_has_a_rollup_destination(self):
        rollup_names = {
            MODULE.normalize_owner_name(name)
            for company in MODULE.COMPANY_PROFILES
            for name in MODULE.configured_rollup_children(company)
        }
        unsafe = [
            (company["canonicalName"], name)
            for company in MODULE.COMPANY_PROFILES
            for name in company.get("suppressProfiles", [])
            if MODULE.normalize_owner_name(name) not in rollup_names
        ]
        self.assertEqual(unsafe, [])

    def test_current_employer_does_not_inherit_historical_breeder_records(self):
        huron = next(
            company
            for company in MODULE.COMPANY_PROFILES
            if company["canonicalName"] == "Huron Plant Technologies LLC"
        )
        self.assertFalse(huron.get("rollupChildren"))

    def test_imida_public_program_is_not_an_alias_of_itum(self):
        itum = next(
            company
            for company in MODULE.COMPANY_PROFILES
            if company["canonicalName"] == "ITUM / IMIDA Table Grape Program"
        )
        self.assertNotIn("IMIDA", itum.get("aliases", []))

    def test_plain_url_research_sources_are_normalized_for_the_dashboard(self):
        research = MODULE.PROFILE_AUDITS[
            MODULE.normalize_alias_search("Laurent Chausset")
        ]
        sources = research.get("webResearchSources") or []
        self.assertTrue(sources)
        self.assertTrue(all(isinstance(source, dict) for source in sources))
        self.assertTrue(all(source.get("url", "").startswith("http") for source in sources))

    def test_researched_official_website_populates_profile_action(self):
        profile = {"ownerName": "Efraim Yosef", "companyWebsite": ""}
        MODULE.apply_profile_audits([profile])
        self.assertEqual(profile["companyWebsite"], "https://yosefsfarm.com/")
        self.assertEqual(profile["candidateParentConfidence"], "high")

    def test_private_company_is_not_public_because_description_names_university_partner(self):
        profile = {
            "ownerName": "Todolivo S.L.",
            "companyDescription": "Private breeder working with the University of Cordoba.",
            "acquisitionScaleClass": "scale_verification_required",
        }
        self.assertFalse(MODULE.institutional_or_public_signal(profile))

    def test_malformed_cotevisa_fragment_is_an_exact_rollup_not_a_broad_alias(self):
        cotevisa = next(
            company
            for company in MODULE.COMPANY_PROFILES
            if company["canonicalName"] == "COTEVISA"
        )
        self.assertNotIn("S.L. Viveros", cotevisa.get("aliases", []))
        self.assertIn("S.L. Viveros", cotevisa.get("rollupChildren", []))


if __name__ == "__main__":
    unittest.main()
