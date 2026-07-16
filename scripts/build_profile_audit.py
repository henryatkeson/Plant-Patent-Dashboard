from __future__ import annotations

import csv
import datetime as dt
import json
import math
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OWNER_PROFILE_PATH = ROOT / "data" / "owner_profiles.json"
COMPANY_PROFILE_PATH = ROOT / "config" / "company_profiles.json"
AUDIT_OVERRIDE_PATH = ROOT / "config" / "company_profile_audits.json"
WEB_RESEARCH_PATHS = sorted((ROOT / "config").glob("profile_web_research*.json"))
SITE_PROBE_PATH = ROOT / "data" / "company_site_probe.json"
PATENT_PATH = DATA_DIR / "plant_patents.json"
CPVO_PATH = DATA_DIR / "cpvo_varieties.json"
OUTPUT_JSON = ROOT / "data" / "profile_audit.json"
OUTPUT_CSV = ROOT / "data" / "profile_audit.csv"
CONFIDENCE_JSON = ROOT / "data" / "data_confidence.json"
CONFIDENCE_CSV = ROOT / "data" / "data_confidence.csv"
ROLLUP_REVIEW_CSV = ROOT / "data" / "rollup_review_queue.csv"


PUBLIC_ORG_TERMS = {
    "agriculture",
    "agricultural",
    "academy",
    "academie",
    "center",
    "centre",
    "department",
    "division",
    "federal",
    "foundation",
    "institute",
    "institut",
    "instituto",
    "instytut",
    "investigacion",
    "ministry",
    "nacional",
    "national",
    "research",
    "service",
    "state",
    "universidad",
    "universita",
    "universiteit",
    "university",
    "usda",
}

LEGAL_ENTITY_TERMS = {
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
    "sas",
    "sociedad",
}

ENTITY_HINT_TERMS = {
    "agro",
    "allberry",
    "association",
    "berry",
    "breeding",
    "cerasina",
    "company",
    "fruit",
    "genetic",
    "genetics",
    "hortifruit",
    "nursery",
    "pepiniere",
    "pépinière",
    "sciences",
    "selections",
    "vision",
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
    overrides: dict[str, dict[str, Any]] = {}
    for path in (AUDIT_OVERRIDE_PATH, *WEB_RESEARCH_PATHS):
        payload = read_json(path, {})
        rows = payload.get("profiles", payload) if isinstance(payload, dict) else payload
        for row in rows or []:
            name = clean_text(row.get("canonicalName") or row.get("ownerName"))
            if not name:
                continue
            key = normalize_name(name)
            overrides[key] = {**overrides.get(key, {}), **row}
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


def load_records(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path, {})
    return payload.get("records", []) if isinstance(payload, dict) else []


def count_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes"}


def ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


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
        label = clean_text(item.get("label")) if isinstance(item, dict) else "Evidence"
        url = clean_text(item.get("url")) if isinstance(item, dict) else clean_text(item)
        if url:
            chunks.append(f"{label or 'Evidence'} <{url}>")
    return " | ".join(chunks)


def summarize_keyword_counts(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return " | ".join(f"{key}:{value}" for key, value in sorted(value.items()))


def evidence_url(row: dict[str, Any]) -> str:
    return clean_text(row.get("sourceUrl") or row.get("gazetteUrl"))


def short_record_label(row: dict[str, Any]) -> str:
    chunks = [
        clean_text(row.get("date")),
        clean_text(row.get("crop")),
        clean_text(row.get("cultivar") or row.get("title")),
        clean_text(row.get("primarySource")),
    ]
    return " - ".join(chunk for chunk in chunks if chunk)


def owner_mentioned(owner_name: str, value: Any) -> bool:
    owner = normalize_name(owner_name)
    haystack = normalize_name(value)
    return bool(owner and owner in haystack)


def entity_hint_from_breeder_text(
    owner_name: str,
    text: Any,
    company_by_alias: dict[str, dict[str, Any]],
) -> str:
    raw = clean_text(text)
    if not raw or not owner_mentioned(owner_name, raw):
        return ""
    pieces = [
        clean_text(piece)
        for piece in re.split(r"\s*;\s*", raw)
        if clean_text(piece)
    ]
    for piece in pieces:
        if owner_mentioned(owner_name, piece):
            continue
        company = company_for_owner(piece, {}, company_by_alias)
        if company:
            return clean_text(company.get("canonicalName"))
        normalized = normalize_name(piece)
        if set(normalized.split()) & ENTITY_HINT_TERMS:
            return piece
    return ""


def collect_raw_evidence(
    owner_name: str,
    plant_records: list[dict[str, Any]],
    cpvo_records: list[dict[str, Any]],
    company_by_alias: dict[str, dict[str, Any]],
    limit: int = 5,
) -> dict[str, Any]:
    role_counts: dict[str, int] = {"assignee": 0, "breeder": 0, "inventor": 0, "cpvoBreeder": 0}
    examples: list[dict[str, Any]] = []
    parent_hints: list[str] = []
    for row in plant_records:
        matched_roles = []
        if owner_mentioned(owner_name, row.get("assignee")):
            matched_roles.append("assignee")
            role_counts["assignee"] += 1
        if owner_mentioned(owner_name, row.get("breeders")):
            matched_roles.append("breeder")
            role_counts["breeder"] += 1
        if owner_mentioned(owner_name, row.get("inventors")):
            matched_roles.append("inventor")
            role_counts["inventor"] += 1
        if not matched_roles:
            continue
        hint = entity_hint_from_breeder_text(owner_name, row.get("breeders"), company_by_alias)
        if hint:
            parent_hints.append(hint)
        if len(examples) < limit:
            examples.append(
                {
                    "system": "USPTO",
                    "roles": matched_roles,
                    "label": short_record_label(row),
                    "assignee": clean_text(row.get("assignee")),
                    "breeders": clean_text(row.get("breeders")),
                    "url": evidence_url(row),
                    "candidateParentHint": hint,
                }
            )
    for row in cpvo_records:
        if not owner_mentioned(owner_name, row.get("breeders")):
            continue
        role_counts["cpvoBreeder"] += 1
        if len(examples) < limit:
            examples.append(
                {
                    "system": "CPVO",
                    "roles": ["cpvoBreeder"],
                    "label": short_record_label(row),
                    "assignee": "",
                    "breeders": clean_text(row.get("breeders")),
                    "url": "",
                    "candidateParentHint": "",
                }
            )
    hint_counts: dict[str, int] = {}
    for hint in parent_hints:
        hint_counts[hint] = hint_counts.get(hint, 0) + 1
    best_hint = ""
    if hint_counts:
        best_hint = max(hint_counts, key=lambda hint: (hint_counts[hint], len(hint)))
    return {
        "rawRoleCounts": role_counts,
        "examples": examples,
        "candidateParentHint": best_hint,
        "candidateParentHintCount": hint_counts.get(best_hint, 0),
    }


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
        "ownership_not_verified": 10,
        "web_research_incomplete": 8,
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
    if "ownership_not_verified" in issues or "web_research_incomplete" in issues:
        return "Verify ownership, parent-company status, and official company sources before acquisition review."
    if "trademark_not_checked" in issues:
        return "Run trademark/brand search for the top cultivar and trade names."
    return "No urgent action; revisit after higher-priority profiles."


def ownership_status(legal_count: int, breeder_count: int, inventor_count: int) -> str:
    if legal_count and breeder_count:
        return "mixed_legal_owner_and_breeder_signal"
    if legal_count:
        return "confirmed_legal_owner"
    if breeder_count:
        return "breeder_only_signal"
    if inventor_count:
        return "inventor_only_signal"
    return "unknown_owner_signal"


def confidence_score_and_gate(
    *,
    is_company_profile: bool,
    is_parent_rollup: bool,
    is_individual: bool,
    entity_like: bool,
    public_org: bool,
    legal_count: int,
    breeder_count: int,
    inventor_count: int,
    relevant_count: int,
    protected_count: int,
    website: str,
    contact_url: str,
    linkedin: str,
    site_probe: dict[str, Any],
    override: dict[str, Any],
    issues: list[str],
    candidate_parent: str,
) -> tuple[int, str, str, list[str]]:
    score = 15
    reasons: list[str] = []

    owner_status = ownership_status(legal_count, breeder_count, inventor_count)
    if legal_count:
        score += 26
        reasons.append("legal-owner evidence present")
    if relevant_count and ratio(legal_count, relevant_count) >= 0.5:
        score += 12
        reasons.append("legal-owner evidence covers most relevant records")
    if protected_count:
        score += 8
        reasons.append("protected IP present")
    if is_company_profile:
        score += 14
        reasons.append("seeded company profile")
    if is_parent_rollup:
        score += 6
        reasons.append("explicit rollup profile")
    if website:
        score += 8
        reasons.append("company website linked")
    if site_probe.get("ok") is True:
        score += 6
        reasons.append("website probe passed")
    if contact_url or public_org:
        score += 4
        reasons.append("contact path present or public program")
    if linkedin:
        score += 2
        reasons.append("LinkedIn URL captured")

    audit_confidence = clean_text(override.get("auditConfidence")).lower()
    if audit_confidence == "high":
        score += 10
        reasons.append("manual audit confidence high")
    elif audit_confidence == "medium":
        score += 5
        reasons.append("manual audit confidence medium")
    elif audit_confidence == "low":
        score -= 5
        reasons.append("manual audit confidence low")

    if owner_status == "breeder_only_signal" and breeder_count >= 25:
        penalty = 14 if entity_like or public_org else 24
        score -= penalty
        reasons.append("high-count breeder-only signal")
    if candidate_parent:
        score -= 8
        reasons.append("candidate parent needs holder verification")
    if is_individual and legal_count == 0 and breeder_count >= 10:
        score -= 10
        reasons.append("individual profile without legal-owner evidence")
    if "missing_website" in issues:
        score -= 12
        reasons.append("missing company website")
    if "website_count_mismatch" in issues:
        score -= 8
        reasons.append("website count mismatch")
    if "likely_duplicate_or_rollup" in issues:
        score -= 12
        reasons.append("possible duplicate or incomplete rollup")

    score = max(0, min(100, score))
    if score >= 75:
        tier = "high"
    elif score >= 55:
        tier = "medium"
    elif score >= 35:
        tier = "low"
    else:
        tier = "unverified"

    if public_org:
        gate = "public_program_reference"
    elif owner_status in {"confirmed_legal_owner", "mixed_legal_owner_and_breeder_signal"} and is_company_profile:
        gate = "ready_for_business_review"
    elif owner_status in {"confirmed_legal_owner", "mixed_legal_owner_and_breeder_signal"}:
        gate = "legal_owner_needs_company_profile"
    elif not is_company_profile and entity_like and owner_status == "breeder_only_signal":
        gate = "legal_entity_profile_needed"
    elif candidate_parent or "high_count_breeder_only_profile" in issues:
        gate = "holder_verification_required"
    elif is_company_profile:
        gate = "company_profile_needs_enrichment"
    else:
        gate = "triage_queue"
    return score, tier, gate, reasons


def build_raw_evidence_map(
    profiles: list[dict[str, Any]],
    plant_records: list[dict[str, Any]],
    cpvo_records: list[dict[str, Any]],
    company_by_alias: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    owner_names: dict[str, str] = {}
    token_index: dict[str, set[str]] = {}
    for profile in profiles:
        owner_name = clean_text(profile.get("ownerName"))
        if not owner_name:
            continue
        record_count = count_value(profile.get("recordCount"))
        legal_count = count_value(profile.get("legalOwnerRecordCount"))
        breeder_count = count_value(profile.get("breederSignalRecordCount"))
        is_individual = bool_value(profile.get("individualOwner"))
        needs_raw_evidence = (
            record_count >= 20
            or breeder_count >= 10
            or legal_count > 0
            or is_individual
        )
        if not needs_raw_evidence:
            continue
        owner_normalized = normalize_name(owner_name)
        if not owner_normalized:
            continue
        owner_names[owner_normalized] = owner_name
        output[owner_normalized] = {
            "rawRoleCounts": {"assignee": 0, "breeder": 0, "inventor": 0, "cpvoBreeder": 0},
            "examples": [],
            "candidateParentHintCounts": {},
        }
        for token in set(owner_normalized.split()):
            if len(token) >= 4:
                token_index.setdefault(token, set()).add(owner_normalized)

    def candidate_owners(value: Any) -> set[str]:
        normalized = normalize_name(value)
        tokens = set(normalized.split())
        candidates: set[str] = set()
        for token in tokens:
            candidates.update(token_index.get(token, set()))
        return {owner for owner in candidates if owner in normalized}

    def add_example(owner: str, example: dict[str, Any], limit: int = 5) -> None:
        examples = output[owner]["examples"]
        if len(examples) < limit:
            examples.append(example)

    for row in plant_records:
        matched: dict[str, list[str]] = {}
        for role, field in (("assignee", "assignee"), ("breeder", "breeders"), ("inventor", "inventors")):
            for owner in candidate_owners(row.get(field)):
                matched.setdefault(owner, []).append(role)
                output[owner]["rawRoleCounts"][role] += 1
        for owner, roles in matched.items():
            hint = entity_hint_from_breeder_text(owner_names[owner], row.get("breeders"), company_by_alias)
            if hint:
                hints = output[owner]["candidateParentHintCounts"]
                hints[hint] = hints.get(hint, 0) + 1
            add_example(
                owner,
                {
                    "system": "USPTO",
                    "roles": roles,
                    "label": short_record_label(row),
                    "assignee": clean_text(row.get("assignee")),
                    "breeders": clean_text(row.get("breeders")),
                    "url": evidence_url(row),
                    "candidateParentHint": hint,
                },
            )

    for row in cpvo_records:
        for owner in candidate_owners(row.get("breeders")):
            output[owner]["rawRoleCounts"]["cpvoBreeder"] += 1
            add_example(
                owner,
                {
                    "system": "CPVO",
                    "roles": ["cpvoBreeder"],
                    "label": short_record_label(row),
                    "assignee": "",
                    "breeders": clean_text(row.get("breeders")),
                    "url": "",
                    "candidateParentHint": "",
                },
            )

    for owner, evidence in output.items():
        hint_counts = evidence.pop("candidateParentHintCounts", {})
        best_hint = ""
        if hint_counts:
            best_hint = max(hint_counts, key=lambda hint: (hint_counts[hint], len(hint)))
        evidence["candidateParentHint"] = best_hint
        evidence["candidateParentHintCount"] = hint_counts.get(best_hint, 0)
    return output


def write_confidence_outputs(rows: list[dict[str, Any]]) -> None:
    summary = {
        "title": "Data Confidence Summary",
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "profileCount": len(rows),
        "confidenceTierCounts": {
            tier: sum(1 for row in rows if row["dataConfidenceTier"] == tier)
            for tier in ("high", "medium", "low", "unverified")
        },
        "ownershipStatusCounts": {
            status: sum(1 for row in rows if row["ownershipStatus"] == status)
            for status in sorted({row["ownershipStatus"] for row in rows})
        },
        "actionabilityGateCounts": {
            gate: sum(1 for row in rows if row["actionabilityGate"] == gate)
            for gate in sorted({row["actionabilityGate"] for row in rows})
        },
        "criticalIssues": {
            "holderVerificationRequired": sum(1 for row in rows if row["actionabilityGate"] == "holder_verification_required"),
            "legalEntityProfileNeeded": sum(1 for row in rows if row["actionabilityGate"] == "legal_entity_profile_needed"),
            "legalOwnerNeedsCompanyProfile": sum(1 for row in rows if row["actionabilityGate"] == "legal_owner_needs_company_profile"),
            "readyForBusinessReview": sum(1 for row in rows if row["actionabilityGate"] == "ready_for_business_review"),
        },
        "methodNotes": [
            "Data confidence is separate from sourcing score. It measures how much trust to place in the owner/profile identity.",
            "Confirmed legal-owner records are higher confidence than breeder-only CPVO signals.",
            "Holder-verification rows should not be treated as acquisition targets until a legal owner or company relationship is sourced.",
        ],
    }
    confidence_fields = [
        "ownerName",
        "ownershipStatus",
        "dataConfidenceTier",
        "dataConfidenceScore",
        "actionabilityGate",
        "recordCount",
        "protectedIpCount",
        "legalOwnerRecordCount",
        "breederSignalRecordCount",
        "relevantIpRecordCount",
        "isCompanyProfile",
        "isParentRollup",
        "entityLikeName",
        "publicOrgName",
        "companyWebsite",
        "companyContactUrl",
        "topCrops",
        "topJurisdictions",
        "candidateParent",
        "candidateParentBasis",
        "candidateParentEvidenceUrl",
        "rawEvidenceRoles",
        "rawEvidenceExamples",
        "confidenceReasons",
        "auditIssues",
        "recommendedNextStep",
    ]
    confidence_rows = [
        {field: row.get(field, "") for field in confidence_fields}
        for row in rows
    ]
    CONFIDENCE_JSON.write_text(
        json.dumps({"metadata": summary, "profiles": confidence_rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with CONFIDENCE_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=confidence_fields)
        writer.writeheader()
        writer.writerows(confidence_rows)


def write_rollup_review_queue(rows: list[dict[str, Any]]) -> None:
    review_fields = [
        "ownerName",
        "candidateParent",
        "candidateParentBasis",
        "candidateParentEvidenceUrl",
        "dataConfidenceTier",
        "dataConfidenceScore",
        "actionabilityGate",
        "auditPriority",
        "recordCount",
        "legalOwnerRecordCount",
        "breederSignalRecordCount",
        "topCrops",
        "topJurisdictions",
        "rawEvidenceRoles",
        "rawEvidenceExamples",
        "recommendedNextStep",
    ]
    review_rows = [
        {field: row.get(field, "") for field in review_fields}
        for row in rows
        if row.get("candidateParent")
        or row.get("actionabilityGate") in {"holder_verification_required", "legal_entity_profile_needed", "legal_owner_needs_company_profile"}
        or "likely_duplicate_or_rollup" in str(row.get("auditIssues", ""))
    ]
    review_rows.sort(
        key=lambda row: (
            count_value(row.get("recordCount")),
            count_value(row.get("breederSignalRecordCount")),
            count_value(row.get("dataConfidenceScore")),
        ),
        reverse=True,
    )
    with ROLLUP_REVIEW_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=review_fields)
        writer.writeheader()
        writer.writerows(review_rows)


def build_row(
    profile: dict[str, Any],
    company_by_canonical: dict[str, dict[str, Any]],
    company_by_alias: dict[str, dict[str, Any]],
    overrides: dict[str, dict[str, Any]],
    site_probes: dict[str, dict[str, Any]],
    raw_evidence: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    owner_name = clean_text(profile.get("ownerName"))
    company = company_for_owner(owner_name, company_by_canonical, company_by_alias)
    override = profile_override(owner_name, overrides)
    record_count = count_value(profile.get("recordCount"))
    protected_count = count_value(profile.get("protectedIpCount"))
    legal_count = count_value(profile.get("legalOwnerRecordCount"))
    breeder_count = count_value(profile.get("breederSignalRecordCount"))
    inventor_count = count_value(profile.get("inventorSignalRecordCount"))
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
    entity_like = bool(set(normalized_owner.split()) & LEGAL_ENTITY_TERMS)
    count_comparison = compare_website_count(record_count, protected_count, override)
    evidence = raw_evidence.get(normalized_owner, {})
    auto_parent_hint = clean_text(evidence.get("candidateParentHint"))

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
    trademark_status = clean_text(override.get("trademarkStatus")).lower()
    if is_company_profile and trademark_status in {"", "not_checked", "not reviewed"}:
        issues.append("trademark_not_checked")
    web_research_status = clean_text(override.get("webResearchStatus")).lower()
    if is_company_profile and web_research_status not in {"verified", "not_actionable_verified"}:
        issues.append("web_research_incomplete")
    if is_company_profile and not clean_text(override.get("ownershipType")):
        issues.append("ownership_not_verified")
    if not is_company_profile and is_parent_rollup and not profile.get("rollupChildren"):
        issues.append("likely_duplicate_or_rollup")

    candidate_parent = clean_text(override.get("candidateParent")) or auto_parent_hint
    confidence_score, confidence_tier, actionability_gate, confidence_reasons = confidence_score_and_gate(
        is_company_profile=is_company_profile,
        is_parent_rollup=is_parent_rollup,
        is_individual=is_individual,
        entity_like=entity_like,
        public_org=public_org,
        legal_count=legal_count,
        breeder_count=breeder_count,
        inventor_count=inventor_count,
        relevant_count=relevant_count,
        protected_count=protected_count,
        website=website,
        contact_url=contact_url,
        linkedin=linkedin,
        site_probe=site_probe,
        override=override,
        issues=issues,
        candidate_parent=candidate_parent,
    )
    priority, priority_score = issue_priority(issues, record_count, score)
    return {
        "ownerName": owner_name,
        "ownershipStatus": ownership_status(legal_count, breeder_count, inventor_count),
        "dataConfidenceTier": confidence_tier,
        "dataConfidenceScore": confidence_score,
        "actionabilityGate": actionability_gate,
        "confidenceReasons": " | ".join(confidence_reasons),
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
        "entityLikeName": entity_like,
        "publicOrgName": public_org,
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
        "webResearchStatus": clean_text(override.get("webResearchStatus")),
        "webResearchReviewedAt": clean_text(override.get("webResearchReviewedAt")),
        "webResearchSources": summarize_links(override.get("webResearchSources")),
        "webResearchNotes": clean_text(override.get("webResearchNotes")),
        "ownershipType": clean_text(override.get("ownershipType")),
        "ownershipSummary": clean_text(override.get("ownershipSummary")),
        "parentCompany": clean_text(override.get("parentCompany")),
        "headquarters": clean_text(override.get("headquarters")),
        "leadershipSummary": clean_text(override.get("leadershipSummary")),
        "candidateParent": candidate_parent,
        "candidateParentBasis": clean_text(override.get("candidateParentBasis")) or (
            f"USPTO breeder string contains entity hint {auto_parent_hint!r}."
            if auto_parent_hint
            else ""
        ),
        "candidateParentEvidenceUrl": clean_text(override.get("candidateParentEvidenceUrl")) or clean_text(
            (evidence.get("examples") or [{}])[0].get("url") if evidence.get("examples") else ""
        ),
        "rawEvidenceRoles": " | ".join(
            f"{key}:{value}"
            for key, value in (evidence.get("rawRoleCounts") or {}).items()
            if value
        ),
        "rawEvidenceExamples": " | ".join(
            f"{example.get('system')}: {example.get('label')} ({', '.join(example.get('roles') or [])})"
            for example in (evidence.get("examples") or [])[:3]
        ),
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
        "primaryContactEmail": clean_text(override.get("primaryContactEmail")),
        "primaryContactPhone": clean_text(override.get("primaryContactPhone")),
        "primaryContactUrl": clean_text(override.get("primaryContactUrl")),
        "contactSourceUrl": clean_text(override.get("contactSourceUrl")),
        "trademarkStatus": clean_text(override.get("trademarkStatus")),
        "trademarkOwner": clean_text(override.get("trademarkOwner")),
        "trademarkEvidenceUrl": clean_text(override.get("trademarkEvidenceUrl")),
        "trademarkLastCheckedAt": clean_text(override.get("trademarkLastCheckedAt")),
        "brandExamples": " | ".join(override.get("brandExamples") or []),
        "auditNotes": clean_text(override.get("auditNotes")),
    }


def main() -> int:
    owner_payload = read_json(OWNER_PROFILE_PATH, {})
    profiles = compact_owner_rows(owner_payload)
    company_by_canonical, company_by_alias = load_company_profiles()
    overrides = load_audit_overrides()
    site_probes = load_site_probes()
    plant_records = load_records(PATENT_PATH)
    cpvo_records = load_records(CPVO_PATH)
    raw_evidence = build_raw_evidence_map(profiles, plant_records, cpvo_records, company_by_alias)
    rows = [
        build_row(profile, company_by_canonical, company_by_alias, overrides, site_probes, raw_evidence)
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
    write_confidence_outputs(rows)
    write_rollup_review_queue(rows)
    print(f"Wrote {OUTPUT_JSON} and {OUTPUT_CSV} with {len(rows):,} audited profiles.")
    print(f"Wrote {CONFIDENCE_JSON}, {CONFIDENCE_CSV}, and {ROLLUP_REVIEW_CSV}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
