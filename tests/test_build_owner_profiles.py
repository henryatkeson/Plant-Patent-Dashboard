import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_owner_profiles", ROOT / "scripts" / "build_owner_profiles.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class OwnerProfileTests(unittest.TestCase):
    def test_person_entity_classification_uses_legal_tokens_not_substrings(self):
        self.assertTrue(MODULE.looks_individual("Kostrikin Ivan ALEKSANDROVICh"))
        self.assertTrue(MODULE.looks_individual("Meleshko Larysa Fedorivna"))
        self.assertTrue(MODULE.looks_individual("Gianfranco Castagnoli"))
        self.assertFalse(MODULE.looks_individual("Berrytech Srl"))
        self.assertFalse(MODULE.looks_individual("Berries Del Oeste S.L."))
        self.assertFalse(MODULE.looks_individual("Fukushima Prefecture"))
        self.assertFalse(MODULE.looks_individual("University of Western Sydney"))

    def test_state_prefixed_address_fragment_is_not_a_person(self):
        self.assertTrue(MODULE.looks_like_address_or_location("Silverton, Or Robert Gabriel"))
        self.assertFalse(MODULE.looks_individual("Silverton, Or Robert Gabriel"))

    def test_cpvo_location_fragment_is_not_a_person(self):
        self.assertTrue(MODULE.looks_like_address_or_location("CERCA DE DELANO"))
        self.assertFalse(MODULE.looks_individual("CERCA DE DELANO"))

    def test_multilingual_entity_and_location_fragments_are_not_people(self):
        for value in [
            "Saint-Jean-sur-Richelieu",
            "Berrytech, Italy",
            "Economic Development and Innovation",
            "Sociedad Unipersonal",
            "Pepinieres Et Roseraies",
            "Grant &. Chris -. L. Gardner",
            "Miho Akiba, Koriyama, Japan",
            "STOV Enohrai",
        ]:
            with self.subTest(value=value):
                self.assertFalse(MODULE.looks_individual(value))

    def test_short_company_acronym_does_not_match_personal_name(self):
        self.assertIsNone(MODULE.company_profile_for_name("Tulaieva Maia Ivanivna"))
        self.assertEqual(
            MODULE.company_profile_for_name("MAIA")["canonicalName"],
            "Midwest Apple Improvement Association",
        )

    def test_trailing_comma_does_not_block_person_list_split(self):
        names = MODULE.split_people_or_entities(
            "Abliazova Aia Pavlivna, Tulaieva Maiia Ivanivna, Dokuchaieva IEvheniia Mykolaivna,"
        )
        self.assertEqual(
            names,
            [
                "Abliazova Aia Pavlivna",
                "Tulaieva Maiia Ivanivna",
                "Dokuchaieva IEvheniia Mykolaivna",
            ],
        )

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
        self.assertEqual(result["ownerScopedRecordCount"], 1)
        self.assertEqual(result["ownerScopedProtectedIpCount"], 1)
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

    def test_company_without_holder_evidence_cannot_rank_high_fit(self):
        score, band, _reasons, blockers = MODULE.score_acquisition_fit(
            {
                "recordCount": 25,
                "protectedIpCount": 20,
                "relevantIpRecordCount": 25,
                "activeProtectionCount": 20,
                "recordsLast5Years": 8,
                "cropConcentration": 1.0,
                "companyWebsite": "https://example.com",
                "companyDescription": "Private breeding company",
                "legalOwnerRecordCount": 0,
            }
        )

        self.assertLessEqual(score, 70)
        self.assertEqual(band, "Rights-holder verification needed")
        self.assertIn("No confirmed legal-owner records", blockers)

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

    def test_company_rollup_does_not_absorb_individual_breeder_profile(self):
        original_profiles = MODULE.COMPANY_PROFILES
        MODULE.COMPANY_PROFILES = [{
            "canonicalName": "Example Genetics LLC",
            "rollupChildren": ["Jane Breeder"],
            "suppressProfiles": ["Jane Breeder"],
        }]
        try:
            person = {
                "id": "person",
                "ownerName": "Jane Breeder",
                "normalizedOwnerName": MODULE.normalize_owner_name("Jane Breeder"),
                "individualOwner": True,
                "recordCount": 4,
            }
            output = MODULE.add_parent_rollups([person], {}, {})
        finally:
            MODULE.COMPANY_PROFILES = original_profiles

        self.assertEqual(output, [person])

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

    def test_research_alias_attaches_to_canonical_person(self):
        research = MODULE.PROFILE_AUDITS[
            MODULE.normalize_alias_search("Peter Stefan Boches")
        ]
        self.assertEqual(research["canonicalName"], "Boches Peter Stefan")
        self.assertIn("Fall Creek", research["ownershipSummary"])

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

    def test_affiliation_does_not_transfer_person_records_to_company(self):
        person = {
            "id": MODULE.owner_id(MODULE.normalize_owner_name("Jane Breeder")),
            "ownerName": "Jane Breeder",
            "normalizedOwnerName": MODULE.normalize_owner_name("Jane Breeder"),
            "recordCount": 9,
        }
        company = {
            "id": MODULE.owner_id(MODULE.normalize_owner_name("Example Genetics LLC")),
            "ownerName": "Example Genetics LLC",
            "normalizedOwnerName": MODULE.normalize_owner_name("Example Genetics LLC"),
            "recordCount": 3,
        }
        MODULE.apply_breeder_affiliations(
            [person, company],
            [{
                "breederId": person["id"],
                "breederName": "Jane Breeder",
                "normalizedBreederName": person["normalizedOwnerName"],
                "companyName": "Example Genetics LLC",
                "relationshipType": "employment",
                "identityConfidence": "high",
                "relationshipConfidence": "high",
                "status": "verified_relationship",
                "basis": "Official biography",
                "source": "manual ledger",
                "directEvidenceCount": 1,
                "directEvidenceShare": 1.0,
                "rightsBasis": "none",
                "rightsRecordIds": [],
                "evidenceRecordIds": ["TEST-1"],
                "evidence": [],
            }],
        )

        self.assertEqual(person["affiliatedCompany"], "Example Genetics LLC")
        self.assertEqual(company["affiliatedBreederCount"], 1)
        self.assertEqual(company["recordCount"], 3)
        self.assertEqual(company["affiliatedBreeders"][0]["rightsBasis"], "none")


if __name__ == "__main__":
    unittest.main()
