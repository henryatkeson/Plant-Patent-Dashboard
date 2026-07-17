#!/usr/bin/env python3
"""Validate dashboard data contracts and write a machine-readable refresh health report."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
HEALTH_PATH = DATA / "refresh_health.json"


def read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def compact_count(payload: dict[str, Any], key: str) -> int:
    rows = payload.get(key)
    return len(rows) if isinstance(rows, list) else 0


def valid_url(value: Any) -> bool:
    return not value or clean(value).startswith(("https://", "http://"))


def add_check(
    checks: list[dict[str, Any]],
    name: str,
    ok: bool,
    detail: str,
    *,
    severity: str = "error",
) -> None:
    checks.append({"name": name, "ok": ok, "severity": severity, "detail": detail})


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate generated dashboard data.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on critical data-contract failures.")
    args = parser.parse_args()

    patents = read_json(DATA / "plant_patents.json", {})
    cpvo = read_json(DATA / "cpvo_varieties.json", {})
    owners = read_json(DATA / "owner_profiles.json", {})
    affiliations = read_json(DATA / "breeder_affiliations.json", {})
    audit = read_json(DATA / "profile_audit.json", {})
    research = read_json(DATA / "web_research_queue.json", {})
    probes = read_json(DATA / "company_site_probe.json", {})
    evidence_probes = read_json(DATA / "profile_evidence_probe.json", {})
    companies = read_json(ROOT / "config" / "company_profiles.json", [])
    manual_audits_payload = read_json(ROOT / "config" / "company_profile_audits.json", {})
    manual_audits = manual_audits_payload.get("profiles", []) if isinstance(manual_audits_payload, dict) else manual_audits_payload
    web_evidence = []
    for path in sorted((ROOT / "config").glob("profile_web_research*.json")):
        web_evidence_payload = read_json(path, {})
        web_evidence.extend(
            web_evidence_payload.get("profiles", [])
            if isinstance(web_evidence_payload, dict)
            else web_evidence_payload
        )

    patent_count = compact_count(patents, "records")
    cpvo_count = compact_count(cpvo, "records")
    owner_count = compact_count(owners, "owners")
    owner_fields = owners.get("ownerFields", []) if isinstance(owners, dict) else []
    owner_rows = [
        dict(zip(owner_fields, row))
        for row in owners.get("owners", [])
    ] if owner_fields else owners.get("owners", [])
    affiliation_rows = affiliations.get("affiliations", []) if isinstance(affiliations, dict) else []
    affiliation_count = len(affiliation_rows)
    audit_count = compact_count(audit, "profiles")
    research_count = compact_count(research, "profiles")
    checks: list[dict[str, Any]] = []

    add_check(checks, "patent_dataset_present", patent_count >= 100, f"{patent_count:,} plant-patent rows")
    add_check(checks, "cpvo_dataset_present", cpvo_count >= 100, f"{cpvo_count:,} CPVO rows")
    add_check(checks, "owner_profiles_present", owner_count >= 100, f"{owner_count:,} owner profiles")
    add_check(checks, "breeder_affiliations_present", affiliation_count >= 100, f"{affiliation_count:,} breeder relationships")

    valid_affiliation_statuses = {
        "verified_relationship",
        "probable_relationship",
        "review_required",
        "unresolved",
    }
    valid_affiliation_confidence = {"high", "medium", "low", "unverified"}
    invalid_affiliations = [
        clean(row.get("breederName"))
        for row in affiliation_rows
        if clean(row.get("status")) not in valid_affiliation_statuses
        or clean(row.get("identityConfidence")) not in valid_affiliation_confidence
        or clean(row.get("relationshipConfidence")) not in valid_affiliation_confidence
    ]
    add_check(
        checks,
        "breeder_affiliation_enums_valid",
        not invalid_affiliations,
        "All affiliation statuses and confidence values are valid"
        if not invalid_affiliations
        else "Invalid affiliation rows: " + ", ".join(invalid_affiliations[:10]),
    )
    verified_with_weak_identity = [
        clean(row.get("breederName"))
        for row in affiliation_rows
        if clean(row.get("status")) == "verified_relationship"
        and clean(row.get("identityConfidence")) != "high"
    ]
    add_check(
        checks,
        "verified_affiliations_have_verified_identity",
        not verified_with_weak_identity,
        "Every verified relationship also has high-confidence identity"
        if not verified_with_weak_identity
        else "Weak identities marked verified: " + ", ".join(verified_with_weak_identity[:10]),
    )
    known_false_identities = {
        normalize(value)
        for value in (
            "Saint-Jean-sur-Richelieu",
            "Italy Berrytech",
            "Economic Development and Innovation",
            "Sociedad Unipersonal",
            "Pepinieres Et Roseraies",
            "Grant &. Chris -. L. Gardner",
            "Koriyama, Japan Miho Akiba",
            "STOV Enohrai",
        )
    }
    false_identity_rows = [
        clean(row.get("breederName"))
        for row in affiliation_rows
        if normalize(row.get("breederName")) in known_false_identities
    ]
    add_check(
        checks,
        "known_registry_fragments_are_not_breeders",
        not false_identity_rows,
        "Known location and organization fragments are excluded from breeder identities"
        if not false_identity_rows
        else "False breeder identities: " + ", ".join(false_identity_rows),
    )
    self_affiliations = [
        clean(row.get("breederName"))
        for row in affiliation_rows
        if clean(row.get("companyName"))
        and normalize(row.get("breederName")) == normalize(row.get("companyName"))
    ]
    add_check(
        checks,
        "breeders_are_not_affiliated_to_themselves",
        not self_affiliations,
        "No self-referential breeder affiliations"
        if not self_affiliations
        else "Self affiliations: " + ", ".join(self_affiliations[:10]),
    )

    source_record_ids = {
        clean(row.get("id"))
        for row in [*(patents.get("records") or []), *(cpvo.get("records") or [])]
        if clean(row.get("id"))
    }
    unscoped_rights = []
    unknown_rights_records = []
    for row in affiliation_rows:
        rights_basis = clean(row.get("rightsBasis")) or "none"
        rights_ids = [clean(value) for value in row.get("rightsRecordIds") or [] if clean(value)]
        if rights_basis == "none" and rights_ids:
            unscoped_rights.append(clean(row.get("breederName")))
        if rights_basis != "none" and not rights_ids:
            unscoped_rights.append(clean(row.get("breederName")))
        unknown = sorted(set(rights_ids) - source_record_ids)
        if unknown:
            unknown_rights_records.append(f"{clean(row.get('breederName'))}: {unknown[0]}")
    add_check(
        checks,
        "affiliation_rights_are_record_scoped",
        not unscoped_rights,
        "Affiliation never implies ownership without record-specific assignee or holder evidence"
        if not unscoped_rights
        else "Unscoped rights claims: " + ", ".join(unscoped_rights[:10]),
    )
    add_check(
        checks,
        "affiliation_rights_records_exist",
        not unknown_rights_records,
        "All scoped rights records exist in a source dataset"
        if not unknown_rights_records
        else "Unknown rights records: " + ", ".join(unknown_rights_records[:10]),
    )

    invalid_owner_scopes = []
    for row in owner_rows:
        legal = int(row.get("legalOwnerRecordCount") or 0)
        scoped = int(row.get("ownerScopedRecordCount") or 0)
        protected = int(row.get("ownerScopedProtectedIpCount") or 0)
        cliff = int(row.get("ownerScopedExpirationNext5Years") or 0)
        if scoped > legal or protected > scoped or cliff > protected:
            invalid_owner_scopes.append(clean(row.get("ownerName")))
    add_check(
        checks,
        "owner_scoped_portfolios_follow_title_evidence",
        not invalid_owner_scopes,
        "Owner-scoped portfolio and cliff counts never exceed confirmed title evidence"
        if not invalid_owner_scopes
        else "Invalid owner scopes: " + ", ".join(invalid_owner_scopes[:10]),
    )
    add_check(
        checks,
        "profile_audit_covers_every_owner",
        audit_count == owner_count and owner_count > 0,
        f"{audit_count:,} audit rows for {owner_count:,} owners",
    )
    add_check(
        checks,
        "web_research_covers_every_owner",
        research_count == owner_count and owner_count > 0,
        f"{research_count:,} research rows for {owner_count:,} owners",
    )

    company_names = [normalize(row.get("canonicalName")) for row in companies if clean(row.get("canonicalName"))]
    duplicate_companies = sorted({name for name in company_names if company_names.count(name) > 1})
    add_check(
        checks,
        "unique_company_profiles",
        not duplicate_companies,
        "No duplicate canonical company names" if not duplicate_companies else f"Duplicates: {', '.join(duplicate_companies)}",
    )

    alias_owners: dict[str, set[str]] = {}
    for company in companies:
        canonical = clean(company.get("canonicalName"))
        for alias in [canonical, *(company.get("aliases") or [])]:
            key = normalize(alias)
            if key:
                alias_owners.setdefault(key, set()).add(canonical)
    alias_collisions = {
        alias: sorted(owners_for_alias)
        for alias, owners_for_alias in alias_owners.items()
        if len(owners_for_alias) > 1
    }
    add_check(
        checks,
        "company_aliases_unambiguous",
        not alias_collisions,
        "No company alias maps to more than one profile"
        if not alias_collisions
        else "Ambiguous aliases: " + "; ".join(
            f"{alias} -> {', '.join(names)}" for alias, names in list(alias_collisions.items())[:10]
        ),
    )

    audit_names = [normalize(row.get("canonicalName")) for row in manual_audits if clean(row.get("canonicalName"))]
    duplicate_audits = sorted({name for name in audit_names if audit_names.count(name) > 1})
    add_check(
        checks,
        "unique_manual_audits",
        not duplicate_audits,
        "No duplicate manual audit names" if not duplicate_audits else f"Duplicates: {', '.join(duplicate_audits)}",
    )

    evidence_names = [normalize(row.get("canonicalName")) for row in web_evidence if clean(row.get("canonicalName"))]
    duplicate_evidence = sorted({name for name in evidence_names if evidence_names.count(name) > 1})
    add_check(
        checks,
        "unique_web_research_evidence",
        not duplicate_evidence,
        "No duplicate web-research evidence names" if not duplicate_evidence else f"Duplicates: {', '.join(duplicate_evidence)}",
    )

    incomplete_research = [
        clean(row.get("canonicalName"))
        for row in web_evidence
        if not clean(row.get("webResearchStatus"))
        or not clean(row.get("ownershipType"))
        or not clean(row.get("ownershipSummary"))
    ]
    add_check(
        checks,
        "web_research_has_ownership_context",
        not incomplete_research,
        "Every researched profile has status and ownership context"
        if not incomplete_research
        else "Incomplete research rows: " + ", ".join(incomplete_research[:10]),
    )

    source_less_research = []
    for row in web_evidence:
        status = clean(row.get("webResearchStatus")).lower()
        sources = row.get("webResearchSources") or []
        source_optional = any(
            marker in status
            for marker in ("unresolved", "regulator_or_patent_only", "wrong_domain", "legacy_review")
        )
        if not sources and not source_optional:
            source_less_research.append(clean(row.get("canonicalName")))
    add_check(
        checks,
        "completed_web_research_has_sources",
        not source_less_research,
        "Completed research rows include source evidence"
        if not source_less_research
        else "Source-less research rows: " + ", ".join(source_less_research[:10]),
    )

    bad_urls = []
    for company in companies:
        for field in ("website", "contactUrl", "linkedinUrl", "sourceUrl"):
            if not valid_url(company.get(field)):
                bad_urls.append(f"{company.get('canonicalName')}: {field}")
        for link in company.get("newsLinks") or []:
            if not valid_url(link.get("url")):
                bad_urls.append(f"{company.get('canonicalName')}: newsLinks")
    for row in web_evidence:
        for field in ("primaryContactUrl", "contactSourceUrl", "websiteCultivarEvidenceUrl", "candidateParentEvidenceUrl", "trademarkEvidenceUrl"):
            if not valid_url(row.get(field)):
                bad_urls.append(f"{row.get('canonicalName')}: {field}")
        for link in row.get("webResearchSources") or []:
            url = link.get("url") if isinstance(link, dict) else link
            if not valid_url(url):
                bad_urls.append(f"{row.get('canonicalName')}: webResearchSources")
    add_check(
        checks,
        "company_urls_well_formed",
        not bad_urls,
        "All configured URLs use HTTP(S)" if not bad_urls else "Malformed: " + ", ".join(bad_urls[:10]),
    )

    probe_rows = probes.get("companies", []) if isinstance(probes, dict) else []
    wrong_sites = [
        clean(row.get("canonicalName"))
        for row in probe_rows
        if clean(row.get("relevanceStatus")) == "wrong_site_suspected"
    ]
    add_check(
        checks,
        "no_suspected_wrong_company_sites",
        not wrong_sites,
        "No configured site looks like an unrelated business" if not wrong_sites else "Review: " + ", ".join(wrong_sites),
    )

    failed_sites = [
        clean(row.get("canonicalName"))
        for row in probe_rows
        if row.get("website") and not row.get("ok")
    ]
    add_check(
        checks,
        "configured_sites_reachable",
        not failed_sites,
        "All configured sites responded" if not failed_sites else "Unreachable: " + ", ".join(failed_sites),
        severity="warning",
    )

    failed_evidence = [
        row
        for row in evidence_probes.get("links", [])
        if not row.get("ok")
    ] if isinstance(evidence_probes, dict) else []
    add_check(
        checks,
        "profile_evidence_links_reachable",
        not failed_evidence,
        "All automatically checked profile evidence links responded"
        if not failed_evidence
        else f"{len(failed_evidence)} evidence links need replacement or manual review",
        severity="warning",
    )

    research_meta = research.get("metadata", {}) if isinstance(research, dict) else {}
    status_total = sum(int(value or 0) for value in (research_meta.get("statusCounts") or {}).values())
    add_check(
        checks,
        "research_status_totals_match",
        status_total == research_count,
        f"Status totals {status_total:,}; research rows {research_count:,}",
    )

    errors = [check for check in checks if not check["ok"] and check["severity"] == "error"]
    warnings = [check for check in checks if not check["ok"] and check["severity"] == "warning"]
    payload = {
        "metadata": {
            "title": "Dashboard Refresh Health",
            "checkedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
            "status": "failed" if errors else ("warning" if warnings else "healthy"),
            "errorCount": len(errors),
            "warningCount": len(warnings),
        },
        "counts": {
            "plantPatents": patent_count,
            "cpvoRecords": cpvo_count,
            "ownerProfiles": owner_count,
            "breederAffiliations": affiliation_count,
            "companyProfiles": len(companies),
            "manualAudits": len(manual_audits),
            "webEvidenceProfiles": len(web_evidence),
            "profileEvidenceLinks": len(evidence_probes.get("links", [])) if isinstance(evidence_probes, dict) else 0,
            "webResearchRows": research_count,
        },
        "checks": checks,
    }
    HEALTH_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Dashboard data health: {payload['metadata']['status']} ({len(errors)} errors, {len(warnings)} warnings)")
    for check in errors + warnings:
        print(f"- {check['name']}: {check['detail']}")
    return 1 if args.strict and errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
