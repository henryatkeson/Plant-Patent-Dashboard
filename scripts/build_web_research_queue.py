#!/usr/bin/env python3
"""Build a durable, resumable web-research ledger for every owner profile."""

from __future__ import annotations

import csv
import datetime as dt
import json
import math
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
OWNER_PATH = ROOT / "data" / "owner_profiles.json"
COMPANY_PATH = ROOT / "config" / "company_profiles.json"
AUDIT_PATH = ROOT / "config" / "company_profile_audits.json"
WEB_RESEARCH_PATHS = sorted((ROOT / "config").glob("profile_web_research*.json"))
PROBE_PATH = ROOT / "data" / "company_site_probe.json"
OUTPUT_JSON = ROOT / "data" / "web_research_queue.json"
OUTPUT_CSV = ROOT / "data" / "web_research_queue.csv"


PUBLIC_TERMS = {
    "academy",
    "agriculture",
    "agricultural",
    "college",
    "department",
    "federal",
    "government",
    "institute",
    "institut",
    "instituto",
    "ministry",
    "national",
    "research",
    "state",
    "university",
    "usda",
}

ENTITY_TERMS = {
    "ag",
    "association",
    "bv",
    "company",
    "corp",
    "corporation",
    "gmbh",
    "group",
    "holding",
    "holdings",
    "inc",
    "limited",
    "llc",
    "ltd",
    "nursery",
    "plc",
    "pty",
    "sa",
    "sarl",
    "sas",
    "sociedad",
}


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize(value: Any) -> str:
    text = clean_text(value).replace("&", " and ")
    text = re.sub(r"['`\u2019]", "", text)
    text = re.sub(r"[^A-Za-z0-9]+", " ", text).lower().strip()
    return re.sub(r"\s+", " ", text)


def read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def compact_owner_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    fields = payload.get("ownerFields") or []
    return [
        {field: row[index] if index < len(row) else "" for index, field in enumerate(fields)}
        for row in payload.get("owners") or []
    ]


def keyed_rows(payload: Any, name_field: str = "canonicalName") -> dict[str, dict[str, Any]]:
    rows = payload.get("profiles", payload) if isinstance(payload, dict) else payload
    result: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        name = clean_text(row.get(name_field) or row.get("ownerName"))
        if name:
            result[normalize(name)] = row
    return result


def company_indexes() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    companies = read_json(COMPANY_PATH, [])
    canonical: dict[str, dict[str, Any]] = {}
    aliases: dict[str, dict[str, Any]] = {}
    for company in companies:
        name = clean_text(company.get("canonicalName"))
        if not name:
            continue
        canonical[normalize(name)] = company
        for alias in [name, *(company.get("aliases") or [])]:
            if normalize(alias):
                aliases[normalize(alias)] = company
    return canonical, aliases


def probe_index() -> dict[str, dict[str, Any]]:
    payload = read_json(PROBE_PATH, {})
    return {
        normalize(row.get("canonicalName")): row
        for row in payload.get("companies", [])
        if normalize(row.get("canonicalName"))
    }


def int_value(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return clean_text(value).lower() in {"1", "true", "yes"}


def host(url: str) -> str:
    if not url:
        return ""
    return urlparse(url).netloc.lower().removeprefix("www.")


def unique_urls(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if isinstance(value, dict):
            value = value.get("url")
        url = clean_text(value)
        if url and url not in seen:
            result.append(url)
            seen.add(url)
    return result


def classify_entity(
    owner: dict[str, Any],
    company: dict[str, Any],
    audit: dict[str, Any],
) -> str:
    name_tokens = set(normalize(owner.get("ownerName")).split())
    if bool_value(owner.get("isParentRollup")) or company:
        return "company_or_rollup"
    if name_tokens & PUBLIC_TERMS:
        return "public_or_institutional"
    if name_tokens & ENTITY_TERMS:
        return "company_candidate"
    if clean_text(audit.get("candidateParent")):
        return "individual_with_candidate_parent"
    if bool_value(owner.get("individualOwner")):
        return "individual_breeder"
    return "unclassified_name"


def research_state(
    owner: dict[str, Any],
    company: dict[str, Any],
    audit: dict[str, Any],
    probe: dict[str, Any],
    entity_class: str,
) -> tuple[str, str]:
    explicit = clean_text(audit.get("webResearchStatus"))
    if explicit:
        level = "complete" if explicit in {"verified", "not_actionable_verified"} else "partial"
        return explicit, level

    confidence = clean_text(audit.get("auditConfidence")).lower()
    probe_ok = bool_value(probe.get("ok"))
    relevance = clean_text(probe.get("relevanceStatus")).lower()
    website = clean_text(owner.get("companyWebsite") or company.get("website"))
    relevant_count = int_value(owner.get("relevantIpRecordCount"))

    if confidence == "high" and probe_ok and relevance not in {"weak", "wrong_site_suspected"}:
        return "verified", "complete"
    if website and probe_ok and relevance not in {"weak", "wrong_site_suspected"}:
        return "evidence_backed_profile", "partial"
    if website:
        return "known_domain_needs_review", "partial"
    if entity_class == "public_or_institutional":
        return "institutional_affiliation_research", "not_started"
    if entity_class == "individual_with_candidate_parent":
        return "candidate_parent_needs_verification", "not_started"
    if entity_class in {"company_candidate", "company_or_rollup"}:
        return "company_discovery_needed", "not_started"
    if relevant_count <= 0:
        return "non_target_reference", "not_started"
    return "individual_affiliation_research", "not_started"


def priority_score(owner: dict[str, Any], status: str, entity_class: str) -> int:
    relevant = int_value(owner.get("relevantIpRecordCount"))
    protected = int_value(owner.get("protectedIpCount"))
    last_year = int_value(owner.get("lastYear"))
    acquisition = int_value(owner.get("acquisitionFitScore"))
    current_year = dt.datetime.now(dt.timezone.utc).year
    score = min(28, int(math.log2(max(1, relevant) + 1) * 4))
    score += min(18, int(math.log2(max(1, protected) + 1) * 3))
    score += min(24, round(acquisition * 0.24))
    if last_year >= current_year - 3:
        score += 12
    elif last_year >= current_year - 7:
        score += 6
    if entity_class in {"company_candidate", "company_or_rollup"}:
        score += 10
    if status in {"company_discovery_needed", "candidate_parent_needs_verification"}:
        score += 12
    elif status in {"individual_affiliation_research", "institutional_affiliation_research"}:
        score += 6
    elif status == "verified":
        score -= 20
    if relevant <= 0:
        score -= 30
    return max(0, min(100, score))


def search_queries(owner: dict[str, Any], entity_class: str) -> list[str]:
    name = clean_text(owner.get("ownerName"))
    crops = owner.get("topCrops") or []
    crop = clean_text(crops[0].get("crop")) if crops and isinstance(crops[0], dict) else ""
    queries = [f'"{name}" plant breeder varieties']
    if crop:
        queries.append(f'"{name}" {crop} breeding cultivar')
    if entity_class in {"company_candidate", "company_or_rollup"}:
        queries.append(f'"{name}" company ownership contact')
    else:
        queries.append(f'"{name}" breeder company affiliation')
    return queries


def build_row(
    owner: dict[str, Any],
    company: dict[str, Any],
    audit: dict[str, Any],
    probe: dict[str, Any],
) -> dict[str, Any]:
    entity_class = classify_entity(owner, company, audit)
    status, review_level = research_state(owner, company, audit, probe, entity_class)
    website = clean_text(owner.get("companyWebsite") or company.get("website"))
    contact = clean_text(owner.get("companyContactUrl") or company.get("contactUrl"))
    linkedin = clean_text(owner.get("companyLinkedInUrl") or company.get("linkedinUrl"))
    evidence_urls = unique_urls(
        [
            website,
            contact,
            linkedin,
            owner.get("companySourceUrl"),
            audit.get("websiteCultivarEvidenceUrl"),
            audit.get("candidateParentEvidenceUrl"),
            audit.get("contactSourceUrl"),
            *(company.get("newsLinks") or []),
            *(audit.get("webResearchSources") or []),
        ]
    )
    queries = search_queries(owner, entity_class)
    return {
        "ownerName": clean_text(owner.get("ownerName")),
        "entityClass": entity_class,
        "researchStatus": status,
        "reviewLevel": review_level,
        "researchPriorityScore": priority_score(owner, status, entity_class),
        "acquisitionFitScore": int_value(owner.get("acquisitionFitScore")),
        "acquisitionFitBand": clean_text(owner.get("acquisitionFitBand")),
        "recordCount": int_value(owner.get("recordCount")),
        "relevantIpRecordCount": int_value(owner.get("relevantIpRecordCount")),
        "protectedIpCount": int_value(owner.get("protectedIpCount")),
        "lastYear": int_value(owner.get("lastYear")) or "",
        "knownWebsite": website,
        "knownDomain": host(website),
        "knownContactUrl": contact,
        "knownLinkedInUrl": linkedin,
        "candidateParent": clean_text(audit.get("candidateParent")),
        "ownershipType": clean_text(audit.get("ownershipType")),
        "parentCompany": clean_text(audit.get("parentCompany")),
        "primaryContactName": clean_text(audit.get("primaryContactName")),
        "primaryContactEmail": clean_text(audit.get("primaryContactEmail")),
        "primaryContactPhone": clean_text(audit.get("primaryContactPhone")),
        "trademarkStatus": clean_text(audit.get("trademarkStatus")) or "not_checked",
        "sourceCount": len(evidence_urls),
        "sourceUrls": " | ".join(evidence_urls),
        "searchQuery1": queries[0],
        "searchQuery2": queries[1] if len(queries) > 1 else "",
        "searchQuery3": queries[2] if len(queries) > 2 else "",
        "lastWebReviewAt": clean_text(audit.get("webResearchReviewedAt") or probe.get("probedAt")),
        "researchNotes": clean_text(audit.get("webResearchNotes") or audit.get("auditNotes")),
    }


def main() -> int:
    owner_payload = read_json(OWNER_PATH, {})
    owners = compact_owner_rows(owner_payload)
    company_by_canonical, company_by_alias = company_indexes()
    audits = keyed_rows(read_json(AUDIT_PATH, {}))
    for path in WEB_RESEARCH_PATHS:
        for key, row in keyed_rows(read_json(path, {})).items():
            audits[key] = {**audits.get(key, {}), **row}
    probes = probe_index()
    rows = []
    for owner in owners:
        owner_key = normalize(owner.get("ownerName"))
        company = company_by_canonical.get(owner_key) or company_by_alias.get(owner_key) or {}
        company_key = normalize(company.get("canonicalName")) if company else owner_key
        rows.append(
            build_row(
                owner,
                company,
                audits.get(owner_key, {}),
                probes.get(company_key, {}),
            )
        )

    rows.sort(
        key=lambda row: (
            int_value(row.get("researchPriorityScore")),
            int_value(row.get("relevantIpRecordCount")),
            int_value(row.get("recordCount")),
        ),
        reverse=True,
    )
    statuses = sorted({row["researchStatus"] for row in rows})
    levels = sorted({row["reviewLevel"] for row in rows})
    metadata = {
        "title": "Owner Web Research Ledger",
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "profileCount": len(rows),
        "statusCounts": {status: sum(row["researchStatus"] == status for row in rows) for status in statuses},
        "reviewLevelCounts": {level: sum(row["reviewLevel"] == level for row in rows) for level in levels},
        "profilesWithKnownWebsite": sum(bool(row["knownWebsite"]) for row in rows),
        "profilesWithContactPath": sum(bool(row["knownContactUrl"]) for row in rows),
        "profilesWithNamedContact": sum(bool(row["primaryContactName"]) for row in rows),
        "profilesWithTrademarkReview": sum(row["trademarkStatus"] != "not_checked" for row in rows),
        "methodNotes": [
            "Every generated owner or breeder profile receives a research state; no profile is silently omitted.",
            "Automated site probes validate known domains but cannot safely discover an unknown company from a person name without source review.",
            "Search queries are research prompts, not evidence. Only source URLs captured after review should affect profile confidence.",
            "No private contact information is inferred or scraped from gated sources.",
        ],
    }
    OUTPUT_JSON.write_text(
        json.dumps({"metadata": metadata, "profiles": rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {OUTPUT_JSON} and {OUTPUT_CSV} with {len(rows):,} profiles.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
