from __future__ import annotations

import csv
import datetime as dt
import json
import math
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OWNER_PROFILE_PATH = ROOT / "data" / "owner_profiles.json"
COMPANY_PROFILE_PATH = ROOT / "config" / "company_profiles.json"
AUDIT_OVERRIDE_PATH = ROOT / "config" / "company_profile_audits.json"
SITE_PROBE_PATH = ROOT / "data" / "company_site_probe.json"
OUTPUT_JSON = ROOT / "data" / "profile_audit.json"
OUTPUT_CSV = ROOT / "data" / "profile_audit.csv"


PUBLIC_ORG_TERMS = {
    "agriculture",
    "department",
    "division",
    "foundation",
    "institute",
    "ministry",
    "research",
    "service",
    "university",
    "usda",
}


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_name(value: Any) -> str:
    text = clean_text(value).replace("&", " and ")
    text = re.sub(r"['`]", "", text)
    text = re.sub(r"[^A-Za-z0-9]+", " ", text).lower().strip()
    return re.sub(r"\s+", " ", text)


def read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def compact_owner_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    fields = payload.get("ownerFields") or []
    rows = payload.get("owners") or []
    return [{field: row[index] if index < len(row) else "" for index, field in enumerate(fields)} for row in rows]


def load_audit_overrides() -> dict[str, dict[str, Any]]:
    payload = read_json(AUDIT_OVERRIDE_PATH, {})
    rows = payload.get("profiles", payload) if isinstance(payload, dict) else payload
    overrides: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        name = clean_text(row.get("canonicalName") or row.get("ownerName"))
        if name:
            overrides[normalize_name(name)] = row
    return overrides


def load_company_profiles() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    profiles = read_json(COMPANY_PROFILE_PATH, [])
    by_canonical: dict[str, dict[str, Any]] = {}
    by_alias: dict[str, dict[str, Any]] = {}
    for profile in profiles:
        canonical = clean_text(profile.get("canonicalName"))
        if not canonical:
            continue
        by_canonical[normalize_name(canonical)] = profile
        for alias in [canonical, *(profile.get("aliases") or [])]:
            normalized = normalize_name(alias)
            if normalized:
                by_alias[normalized] = profile
    return by_canonical, by_alias


def load_site_probes() -> dict[str, dict[str, Any]]:
    payload = read_json(SITE_PROBE_PATH, {})
    probes: dict[str, dict[str, Any]] = {}
    for row in payload.get("companies", []) if isinstance(payload, dict) else []:
        name = clean_text(row.get("canonicalName"))
        if name:
            probes[normalize_name(name)] = row
    return probes


def count_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes"}


def summarize_top(items: Any, label: str, limit: int = 4) -> str:
    if not isinstance(items, list):
        return ""
    chunks = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        name = clean_text(item.get(label))
        count = count_value(item.get("count"))
        if name:
            chunks.append(f"{name} {count}" if count else name)
    return " | ".join(chunks)


def summarize_links(items: Any, limit: int = 5) -> str:
    if not isinstance(items, list):
        return ""
    chunks = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        label = clean_text(item.get("label")) or "Evidence"
        url = clean_text(item.get("url"))
        if url:
            chunks.append(f"{label} <{url}>")
    return " | ".join(chunks)


def summarize_keyword_counts(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return " | ".join(f"{key}:{value}" for key, value in sorted(value.items()))


def profile_override(owner_name: str, overrides: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return overrides.get(normalize_name(owner_name), {})


def company_for_owner(
    owner_name: str,
    company_by_canonical: dict[str, dict[str, Any]],
    company_by_alias: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    normalized = normalize_name(owner_name)
    if normalized in company_by_canonical:
        return company_by_canonical[normalized]
    return company_by_alias.get(normalized)


def issue_priority(issues: list[str], record_count: int, score: int) -> tuple[str, int]:
    issue_weight = {
        "likely_duplicate_or_rollup": 32,
        "high_count_individual_profile": 28,
        "high_count_breeder_only_profile": 24,
        "missing_company_profile": 22,
        "website_count_mismatch": 20,
        "missing_website": 18,
        "missing_contact": 10,
        "trademark_not_checked": 8,
        "cultivar_count_not_verified": 8,
        "linkedin_not_verified": 3,
    }
    weighted = sum(issue_weight.get(issue, 4) for issue in issues)
    weighted += min(30, round(math.log1p(max(record_count, 0)) * 5))
    weighted += min(12, round(score / 10))
    if weighted >= 72:
        return "critical", weighted
    if weighted >= 50:
        return "high", weighted
    if weighted >= 28:
        return "medium", weighted
    return "low", weighted


def compare_website_count(record_count: int, protected_count: int, override: dict[str, Any]) -> str:
    value = override.get("websiteCultivarCount")
    if value in {"", None}:
        return ""
    try:
        website_count = int(value)
    except (TypeError, ValueError):
        return "manual_review"
    comparison_base = protected_count or record_count
    if comparison_base >= max(12, website_count * 2):
        return "public_website_count_lower_than_ip_records"
    if website_count >= max(12, comparison_base * 2):
        return "public_website_count_higher_than_ip_records"
    return "roughly_in_line"


def recommended_next_step(issues: list[str]) -> str:
    if "likely_duplicate_or_rollup" in issues or "high_count_individual_profile" in issues:
        return "Check raw breeder strings and assign this profile to a parent company only if source evidence is clear."
    if "high_count_breeder_only_profile" in issues:
        return "Find holder/applicant evidence; treat CPVO-only breeder profiles as lower-confidence until verified."
    if "missing_company_profile" in issues or "missing_website" in issues:
        return "Find official website and ownership context before using this as an acquisition target."
    if "website_count_mismatch" in issues:
        return "Compare public cultivar list against patent/PBR records and document why counts differ."
    if "trademark_not_checked" in issues:
        return "Run trademark/brand search for the top cultivar and trade names."
    return "No urgent action; revisit after higher-priority profiles."


def build_row(
    profile: dict[str, Any],
    company_by_canonical: dict[str, dict[str, Any]],
    company_by_alias: dict[str, dict[str, Any]],
    overrides: dict[str, dict[str, Any]],
    site_probes: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    owner_name = clean_text(profile.get("ownerName"))
    company = company_for_owner(owner_name, company_by_canonical, company_by_alias)
    override = profile_override(owner_name, overrides)
    record_count = count_value(profile.get("recordCount"))
    protected_count = count_value(profile.get("protectedIpCount"))
    legal_count = count_value(profile.get("legalOwnerRecordCount"))
    breeder_count = count_value(profile.get("breederSignalRecordCount"))
    relevant_count = count_value(profile.get("relevantIpRecordCount"))
    score = count_value(profile.get("sourcingScore"))
    is_company_profile = bool(company)
    site_probe = site_probes.get(normalize_name((company or {}).get("canonicalName") or owner_name), {})
    is_parent_rollup = bool_value(profile.get("isParentRollup"))
    is_individual = bool_value(profile.get("individualOwner"))
    website = clean_text(profile.get("companyWebsite") or (company or {}).get("website"))
    contact_url = clean_text(profile.get("companyContactUrl") or (company or {}).get("contactUrl"))
    linkedin = clean_text(profile.get("companyLinkedInUrl") or (company or {}).get("linkedinUrl"))
    normalized_owner = normalize_name(owner_name)
    public_org = bool(set(normalized_owner.split()) & PUBLIC_ORG_TERMS)
    count_comparison = compare_website_count(record_count, protected_count, override)

    issues: list[str] = []
    if not is_company_profile and record_count >= 25 and not website:
        issues.append("missing_company_profile")
    if not is_company_profile and is_individual and record_count >= 10:
        issues.append("high_count_individual_profile")
    if not is_company_profile and breeder_count >= 25 and legal_count == 0:
        issues.append("high_count_breeder_only_profile")
    if is_company_profile and not website:
        issues.append("missing_website")
    if is_company_profile and not contact_url and not public_org:
        issues.append("missing_contact")
    if is_company_profile and not linkedin and not public_org:
        issues.append("linkedin_not_verified")
    if is_company_profile and override.get("websiteCultivarCount") in {"", None}:
        issues.append("cultivar_count_not_verified")
    if count_comparison and count_comparison != "roughly_in_line":
        issues.append("website_count_mismatch")
    if is_company_profile and not clean_text(override.get("trademarkStatus")):
        issues.append("trademark_not_checked")
    if not is_company_profile and is_parent_rollup and not profile.get("rollupChildren"):
        issues.append("likely_duplicate_or_rollup")

    priority, priority_score = issue_priority(issues, record_count, score)
    return {
        "ownerName": owner_name,
        "auditPriority": priority,
        "auditPriorityScore": priority_score,
        "sourcingScore": score,
        "recordCount": record_count,
        "protectedIpCount": protected_count,
        "legalOwnerRecordCount": legal_count,
        "breederSignalRecordCount": breeder_count,
        "relevantIpRecordCount": relevant_count,
        "firstYear": profile.get("firstYear") or "",
        "lastYear": profile.get("lastYear") or "",
        "isCompanyProfile": is_company_profile,
        "isParentRollup": is_parent_rollup,
        "individualOwner": is_individual,
        "companyWebsite": website,
        "companyLinkedInUrl": linkedin,
        "companyContactUrl": contact_url,
        "topCrops": summarize_top(profile.get("topCrops"), "crop"),
        "topJurisdictions": summarize_top(profile.get("topJurisdictions"), "jurisdiction"),
        "rollupChildren": " | ".join(profile.get("rollupChildren") or []),
        "auditIssues": " | ".join(issues),
        "recommendedNextStep": clean_text(override.get("recommendedNextStep")) or recommended_next_step(issues),
        "auditStatus": clean_text(override.get("auditStatus")) or ("company_profile_seeded" if is_company_profile else "needs_triage"),
        "auditConfidence": clean_text(override.get("auditConfidence")) or ("medium" if is_company_profile else "low"),
        "candidateParent": clean_text(override.get("candidateParent")),
        "candidateParentBasis": clean_text(override.get("candidateParentBasis")),
        "candidateParentEvidenceUrl": clean_text(override.get("candidateParentEvidenceUrl")),
        "websiteCultivarCount": override.get("websiteCultivarCount", ""),
        "websiteCultivarCountBasis": clean_text(override.get("websiteCultivarCountBasis")),
        "websiteCultivarEvidenceUrl": clean_text(override.get("websiteCultivarEvidenceUrl")),
        "websiteCountComparison": count_comparison,
        "siteProbeOk": site_probe.get("ok", ""),
        "siteProbeStatus": site_probe.get("status", ""),
        "siteProbeTitle": clean_text(site_probe.get("title")),
        "siteProbeFinalUrl": clean_text(site_probe.get("finalUrl")),
        "siteProbeKeywordCounts": summarize_keyword_counts(site_probe.get("keywordCounts")),
        "siteProbeEvidenceLinks": summarize_links(site_probe.get("evidenceLinks")),
        "primaryContactName": clean_text(override.get("primaryContactName")),
        "primaryContactTitle": clean_text(override.get("primaryContactTitle")),
        "primaryContactUrl": clean_text(override.get("primaryContactUrl")),
        "contactSourceUrl": clean_text(override.get("contactSourceUrl")),
        "trademarkStatus": clean_text(override.get("trademarkStatus")),
        "brandExamples": " | ".join(override.get("brandExamples") or []),
        "auditNotes": clean_text(override.get("auditNotes")),
    }


def main() -> int:
    owner_payload = read_json(OWNER_PROFILE_PATH, {})
    profiles = compact_owner_rows(owner_payload)
    company_by_canonical, company_by_alias = load_company_profiles()
    overrides = load_audit_overrides()
    site_probes = load_site_probes()
    rows = [
        build_row(profile, company_by_canonical, company_by_alias, overrides, site_probes)
        for profile in profiles
    ]
    rows.sort(key=lambda row: (row["auditPriorityScore"], row["recordCount"]), reverse=True)

    summary: dict[str, Any] = {
        "title": "Owner Profile Audit Queue",
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "profileCount": len(rows),
        "companyProfileCount": sum(1 for row in rows if row["isCompanyProfile"]),
        "criticalCount": sum(1 for row in rows if row["auditPriority"] == "critical"),
        "highCount": sum(1 for row in rows if row["auditPriority"] == "high"),
        "methodNotes": [
            "This is an internal QA queue for data integrity, not a user-facing sourcing score.",
            "CPVO records are often breeder-led and should not be treated as legal ownership unless separately verified.",
            "Website cultivar counts are manual evidence fields because company websites rarely expose complete machine-readable lists.",
        ],
    }
    OUTPUT_JSON.write_text(
        json.dumps({"metadata": summary, "profiles": rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    fieldnames = list(rows[0]) if rows else []
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {OUTPUT_JSON} and {OUTPUT_CSV} with {len(rows):,} audited profiles.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
