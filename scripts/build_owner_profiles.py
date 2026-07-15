#!/usr/bin/env python3
"""Build owner-level sourcing profiles from patent and CPVO dashboard records."""

from __future__ import annotations

import datetime as dt
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CONFIG_DIR = ROOT / "config"
PATENT_PATH = DATA_DIR / "plant_patents.json"
CPVO_PATH = DATA_DIR / "cpvo_varieties.json"
OUTPUT_PATH = DATA_DIR / "owner_profiles.json"
COMPANY_PROFILE_PATH = CONFIG_DIR / "company_profiles.json"
TODAY = dt.date.today()

LEGAL_TERMS = {
    "inc",
    "inc.",
    "llc",
    "l.l.c.",
    "ltd",
    "ltd.",
    "limited",
    "corp",
    "corp.",
    "corporation",
    "company",
    "co",
    "co.",
    "gmbh",
    "bv",
    "b.v.",
    "s.a.",
    "sa",
    "sas",
    "ag",
    "nv",
    "n.v.",
    "plc",
    "pty",
    "pte",
    "lp",
    "llp",
    "holdings",
    "holding",
}

INSTITUTION_TERMS = {
    "university",
    "college",
    "institute",
    "institut",
    "research",
    "academy",
    "government",
    "department",
    "minister",
    "usda",
    "state of",
}

CPVO_TREE_OR_VINE_CROPS = {
    "almond",
    "apple",
    "apple/quince hybrid",
    "apricot",
    "avocado",
    "cacao",
    "cherry-sweet",
    "cherry-tart",
    "citrus",
    "fig",
    "grape",
    "hazelnut",
    "kiwifruit",
    "mango",
    "nectarine",
    "olive",
    "peach",
    "pear",
    "pecan",
    "pistachio",
    "plum",
    "pomegranate",
    "prunus",
    "quince",
    "walnut",
}

CROP_ATTRACTIVENESS = {
    "strawberry": 9,
    "grape": 9,
    "blueberry": 9,
    "apple": 8,
    "raspberry": 8,
    "blackberry": 8,
    "cherry-sweet": 8,
    "peach": 8,
    "nectarine": 8,
    "citrus": 8,
    "almond": 8,
    "pistachio": 8,
    "avocado": 8,
    "kiwifruit": 7,
    "pear": 7,
    "plum": 7,
    "apricot": 7,
    "walnut": 7,
    "olive": 7,
    "mango": 7,
    "hazelnut": 7,
    "pecan": 7,
}

RELEVANT_SOURCE_CROPS = set(CROP_ATTRACTIVENESS) | {
    "artichoke",
    "asparagus",
    "bean",
    "broccoli",
    "cabbage",
    "carrot",
    "cauliflower",
    "celery",
    "cucumber",
    "eggplant",
    "garlic",
    "lettuce",
    "melon",
    "onion",
    "pea",
    "pepper",
    "potato",
    "spinach",
    "squash",
    "sweetpotato",
    "tomato",
    "watermelon",
}


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("records", [])


def load_company_profiles() -> list[dict[str, Any]]:
    if not COMPANY_PROFILE_PATH.exists():
        return []
    return json.loads(COMPANY_PROFILE_PATH.read_text(encoding="utf-8"))


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_owner_name(name: str) -> str:
    text = clean_text(name)
    text = re.sub(r"\([^)]*\)", " ", text)
    text = text.replace("&", " and ")
    text = re.sub(r"['`’]", "", text)
    text = re.sub(r"[^A-Za-z0-9]+", " ", text).lower().strip()
    parts = [part for part in text.split() if part not in LEGAL_TERMS]
    return " ".join(parts)


def normalize_alias_search(name: str) -> str:
    text = clean_text(name)
    text = text.replace("&", " and ")
    text = re.sub(r"['`’]", "", text)
    text = re.sub(r"[^A-Za-z0-9]+", " ", text).lower().strip()
    parts = [part for part in text.split() if part not in LEGAL_TERMS]
    return " ".join(parts)


COMPANY_PROFILES = load_company_profiles()


def build_company_alias_index() -> list[tuple[str, dict[str, Any]]]:
    index: list[tuple[str, dict[str, Any]]] = []
    for profile in COMPANY_PROFILES:
        aliases = [profile.get("canonicalName", ""), *(profile.get("aliases") or [])]
        for alias in aliases:
            alias_normalized = normalize_alias_search(alias)
            if alias_normalized:
                index.append((alias_normalized, profile))
    return sorted(index, key=lambda item: len(item[0]), reverse=True)


COMPANY_ALIAS_INDEX = build_company_alias_index()


def company_profile_for_name(name: str) -> dict[str, Any] | None:
    normalized = f" {normalize_alias_search(name)} "
    for alias_normalized, profile in COMPANY_ALIAS_INDEX:
        if len(alias_normalized) <= 4:
            if f" {alias_normalized} " in normalized:
                return profile
        elif alias_normalized in normalized:
            return profile
    return None


def company_profiles_for_name(name: str) -> list[dict[str, Any]]:
    normalized = f" {normalize_alias_search(name)} "
    profiles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for alias_normalized, profile in COMPANY_ALIAS_INDEX:
        canonical = profile["canonicalName"]
        if canonical in seen:
            continue
        if len(alias_normalized) <= 4:
            matched = f" {alias_normalized} " in normalized
        else:
            matched = alias_normalized in normalized
        if matched:
            profiles.append(profile)
            seen.add(canonical)
    return profiles


def canonical_owner_name(name: str) -> str:
    text = clean_text(name)
    profile = company_profile_for_name(text)
    if profile:
        return profile["canonicalName"]
    return text


def display_owner_name(name: str) -> str:
    text = canonical_owner_name(name)
    text = re.sub(r"\s*,?\s*\((?:US|CA|GB|AU|NZ|IT|FR|ES|NL|DE|BR|CL|ZA|JP|KR|CN|MX|AR|IL|BE|DK|SE|CH|PL|QZ)\)\s*$", "", text)
    return text.strip(" ,") or "Unknown owner"


def split_people_or_entities(value: str) -> list[str]:
    text = clean_text(value)
    lowered = text.lower()
    if not text or lowered in {"n/a", "na", "none", "unknown"} or lowered.startswith("information not available"):
        return []
    text = text.replace("\\,", ",")
    text = text.replace("^^^", "|")
    text = text.replace(" / ", "|")
    text = re.sub(r"\s*;\s*", "|", text)
    parts = [clean_text(part).strip(" ,") for part in text.split("|")]
    return [part for part in parts if normalize_owner_name(part) not in {"n a", "na", "none", "unknown"}]


def parse_date(value: Any) -> dt.date | None:
    text = clean_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%b. %d, %Y", "%b %d, %Y", "%B %d, %Y", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def add_years(value: dt.date, years: int) -> dt.date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(month=2, day=28, year=value.year + years)


def is_cpvo(row: dict[str, Any]) -> bool:
    return "cpvo" in clean_text(row.get("sourceKind")).lower() or "cpvo" in clean_text(row.get("source")).lower()


def is_us_plant_patent(row: dict[str, Any]) -> bool:
    source_kind = clean_text(row.get("sourceKind")).lower()
    return "issued plant patent" in source_kind or clean_text(row.get("patentNumber")).upper().startswith("PP")


def is_relevant_sourcing_crop(row: dict[str, Any]) -> bool:
    crop = clean_text(row.get("crop")).lower()
    if not crop or "ornamental" in crop:
        return False
    return crop in RELEVANT_SOURCE_CROPS or any(crop.startswith(f"{relevant}-") for relevant in RELEVANT_SOURCE_CROPS)


def expiration_date(row: dict[str, Any]) -> tuple[str, str]:
    if is_us_plant_patent(row):
        filed = parse_date(row.get("filedDateText")) or parse_date(row.get("applicationDate"))
        if filed:
            return add_years(filed, 20).isoformat(), "US plant patent: 20 years from filing date"
    if is_cpvo(row) and clean_text(row.get("registerType")).upper() == "PBR":
        base = parse_date(row.get("grantDate")) or parse_date(row.get("applicationDate")) or parse_date(row.get("date"))
        if base:
            crop = clean_text(row.get("crop")).lower()
            years = 30 if crop in CPVO_TREE_OR_VINE_CROPS else 25
            return add_years(base, years).isoformat(), f"CPVO PBR: estimated {years} years from grant/application date"
    return "", ""


def owner_candidates(row: dict[str, Any]) -> list[tuple[str, str, str]]:
    candidates: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add_from_value(value: str, role: str, confidence: str) -> None:
        for name in split_people_or_entities(value):
            company_profiles = company_profiles_for_name(name)
            names = [profile["canonicalName"] for profile in company_profiles] or [name]
            for expanded_name in names:
                key = (normalize_owner_name(display_owner_name(expanded_name)), role)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append((expanded_name, role, confidence))

    if is_cpvo(row):
        add_from_value(row.get("breeders", ""), "CPVO breeder", "medium")
    else:
        add_from_value(row.get("assignee", ""), "Patent assignee", "high")
        if not candidates:
            add_from_value(row.get("breeders", ""), "Breeder", "medium")
        if not candidates:
            add_from_value(row.get("inventors", ""), "Inventor", "low")
    return candidates


def record_year(row: dict[str, Any]) -> int | None:
    date = parse_date(row.get("date")) or parse_date(row.get("applicationDate")) or parse_date(row.get("issueDate"))
    return date.year if date else None


def jurisdiction(row: dict[str, Any]) -> str:
    if is_cpvo(row):
        return clean_text(row.get("country")) or "CPVO/unknown"
    source = clean_text(row.get("source"))
    if "Canadian" in source:
        return "CA"
    if "Mexican" in source:
        return "MX"
    return "US"


def looks_individual(name: str) -> bool:
    normalized = normalize_owner_name(name)
    if not normalized:
        return False
    if any(term in normalized for term in INSTITUTION_TERMS):
        return False
    if any(term in clean_text(name).lower() for term in LEGAL_TERMS):
        return False
    words = normalized.split()
    return 2 <= len(words) <= 4


def owner_id(normalized_name: str) -> str:
    import hashlib

    return "OWNER-" + hashlib.sha1(normalized_name.encode("utf-8")).hexdigest()[:12].upper()


def score_profile(profile: dict[str, Any]) -> tuple[int, list[str]]:
    record_count = profile["recordCount"]
    protected_count = profile["protectedIpCount"]
    legal_owner_count = profile["legalOwnerRecordCount"]
    relevant_count = profile["relevantIpRecordCount"]
    jurisdictions = len(profile["jurisdictionCounts"])
    latest_year = profile.get("lastYear") or 0
    recency = max(0, min(20, latest_year - 2006)) if latest_year else 0
    scale = min(25, math.log1p(max(record_count, relevant_count)) * 4.5)
    protected = min(20, protected_count / max(1, record_count) * 20)
    jurisdiction_score = min(12, jurisdictions * 2.5)
    velocity = min(12, profile["recordsLast5Years"] * 1.2)
    durability = min(8, profile["activeProtectionCount"] / max(1, protected_count) * 8) if protected_count else 0
    crop_score = max((CROP_ATTRACTIVENESS.get(crop.lower(), 5) for crop in profile["cropCounts"]), default=5)
    legal_confidence = min(12, legal_owner_count * 1.2)
    relevance = min(10, relevant_count * 0.8)
    score = round(scale + protected + jurisdiction_score + velocity + durability + crop_score + legal_confidence + relevance + recency * 0.35)

    flags: list[str] = []
    if legal_owner_count:
        flags.append("Confirmed patent assignee")
    if profile["breederSignalRecordCount"] and not legal_owner_count:
        flags.append("Breeder-led signal")
    if relevant_count:
        flags.append("Relevant crop exposure")
    if profile["individualOwner"]:
        flags.append("Individual owner")
    if profile["soleNamedBreeder"]:
        flags.append("Sole named breeder/inventor")
    if profile["recordsLast5Years"] == 0 and record_count >= 5:
        flags.append("Dormant portfolio")
    if profile["expirationNext5Years"] >= max(2, protected_count * 0.25):
        flags.append("Patent/PBR cliff")
    if profile["cropConcentration"] >= 0.75 and record_count >= 5:
        flags.append("Focused crop program")
    if jurisdictions >= 4:
        flags.append("Multi-jurisdiction program")
    return min(100, score), flags


def build_profiles(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    current_year = TODAY.year

    for row in records:
        year = record_year(row)
        exp_date, exp_basis = expiration_date(row)
        exp = parse_date(exp_date)
        owners = owner_candidates(row)
        if not owners:
            continue

        for raw_owner, owner_role, confidence in owners:
            owner_display = display_owner_name(raw_owner)
            normalized = normalize_owner_name(owner_display)
            if not normalized:
                continue
            company_profile = company_profile_for_name(owner_display)
            profile = grouped.setdefault(
                normalized,
                {
                    "id": owner_id(normalized),
                    "ownerName": owner_display,
                    "normalizedOwnerName": normalized,
                    "companyWebsite": company_profile.get("website", "") if company_profile else "",
                    "companyDescription": company_profile.get("description", "") if company_profile else "",
                    "companySourceUrl": company_profile.get("sourceUrl", "") if company_profile else "",
                    "recordCount": 0,
                    "ownerRoleCounts": Counter(),
                    "confidenceCounts": Counter(),
                    "cropCounts": Counter(),
                    "jurisdictionCounts": Counter(),
                    "sourceKindCounts": Counter(),
                    "registerCounts": Counter(),
                    "statusCounts": Counter(),
                    "years": Counter(),
                    "expirationYears": Counter(),
                    "namedBreeders": Counter(),
                    "namedInventors": Counter(),
                    "sampleRecords": [],
                    "expirationBasisCounts": Counter(),
                    "expirationNext1Year": 0,
                    "expirationNext3Years": 0,
                    "expirationNext5Years": 0,
                    "expiredProtectionCount": 0,
                    "activeProtectionCount": 0,
                    "protectedIpCount": 0,
                    "usPlantPatentCount": 0,
                    "cpvoPbrCount": 0,
                    "legalOwnerRecordCount": 0,
                    "breederSignalRecordCount": 0,
                    "inventorSignalRecordCount": 0,
                    "relevantIpRecordCount": 0,
                    "relevantLegalOwnerRecordCount": 0,
                    "individualOwner": False if company_profile else looks_individual(owner_display),
                },
            )
            if company_profile and not profile.get("companyWebsite"):
                profile["companyWebsite"] = company_profile.get("website", "")
                profile["companyDescription"] = company_profile.get("description", "")
                profile["companySourceUrl"] = company_profile.get("sourceUrl", "")

            profile["recordCount"] += 1
            profile["ownerRoleCounts"][owner_role] += 1
            profile["confidenceCounts"][confidence] += 1
            if owner_role == "Patent assignee":
                profile["legalOwnerRecordCount"] += 1
            elif owner_role in {"CPVO breeder", "Breeder"}:
                profile["breederSignalRecordCount"] += 1
            elif owner_role == "Inventor":
                profile["inventorSignalRecordCount"] += 1
            relevant_crop = is_relevant_sourcing_crop(row)
            if relevant_crop:
                profile["relevantIpRecordCount"] += 1
                if owner_role == "Patent assignee":
                    profile["relevantLegalOwnerRecordCount"] += 1
            profile["cropCounts"][clean_text(row.get("crop")) or "Unclassified"] += 1
            profile["jurisdictionCounts"][jurisdiction(row)] += 1
            profile["sourceKindCounts"][clean_text(row.get("sourceKind")) or clean_text(row.get("source")) or "Unknown"] += 1
            if row.get("registerType"):
                profile["registerCounts"][row["registerType"]] += 1
            if row.get("status"):
                profile["statusCounts"][clean_text(row.get("status"))] += 1
            if year:
                profile["years"][year] += 1

            for breeder in split_people_or_entities(row.get("breeders", "")):
                profile["namedBreeders"][breeder] += 1
            for inventor in split_people_or_entities(row.get("inventors", "")):
                profile["namedInventors"][inventor] += 1

            source_kind = clean_text(row.get("sourceKind")).lower()
            is_protected = is_us_plant_patent(row) or ("plant breeders" in source_kind and clean_text(row.get("registerType")).upper() == "PBR")
            if is_protected:
                profile["protectedIpCount"] += 1
                if is_us_plant_patent(row):
                    profile["usPlantPatentCount"] += 1
                if is_cpvo(row) and clean_text(row.get("registerType")).upper() == "PBR":
                    profile["cpvoPbrCount"] += 1
                if exp:
                    if exp < TODAY:
                        profile["expiredProtectionCount"] += 1
                    else:
                        profile["activeProtectionCount"] += 1
                        days = (exp - TODAY).days
                        if days <= 365:
                            profile["expirationNext1Year"] += 1
                        if days <= 365 * 3:
                            profile["expirationNext3Years"] += 1
                        if days <= 365 * 5:
                            profile["expirationNext5Years"] += 1
                    profile["expirationYears"][exp.year] += 1
                if exp_basis:
                    profile["expirationBasisCounts"][exp_basis] += 1

            if len(profile["sampleRecords"]) < 3:
                profile["sampleRecords"].append(
                    {
                        "date": row.get("date", ""),
                        "crop": row.get("crop", ""),
                        "cultivar": row.get("cultivar") or row.get("title", ""),
                        "sourceKind": row.get("sourceKind", ""),
                        "jurisdiction": jurisdiction(row),
                        "source": row.get("primarySource", ""),
                    }
                )

    profiles: list[dict[str, Any]] = []
    for profile in grouped.values():
        years = sorted(profile["years"])
        first_year = years[0] if years else None
        last_year = years[-1] if years else None
        record_count = profile["recordCount"]
        crop_counts = dict(profile["cropCounts"].most_common())
        top_crop_count = max(crop_counts.values(), default=0)
        profile["firstYear"] = first_year
        profile["lastYear"] = last_year
        profile["recordsLast3Years"] = sum(count for year, count in profile["years"].items() if year >= current_year - 2)
        profile["recordsLast5Years"] = sum(count for year, count in profile["years"].items() if year >= current_year - 4)
        profile["filingVelocity5Year"] = round(profile["recordsLast5Years"] / 5, 2)
        profile["annualCounts"] = [{"year": year, "count": count} for year, count in sorted(profile["years"].items())]
        profile["expirationSchedule"] = [{"year": year, "count": count} for year, count in sorted(profile["expirationYears"].items())]
        profile["cropConcentration"] = round(top_crop_count / record_count, 3) if record_count else 0
        profile["soleNamedBreeder"] = (len(profile["namedBreeders"]) + len(profile["namedInventors"])) == 1 and record_count >= 2
        score, flags = score_profile(profile)
        profile["sourcingScore"] = score
        profile["sourcingFlags"] = flags
        profile["topCrops"] = [{"crop": crop, "count": count} for crop, count in profile["cropCounts"].most_common(6)]
        profile["topJurisdictions"] = [{"jurisdiction": key, "count": value} for key, value in profile["jurisdictionCounts"].most_common(8)]
        profile["topBreeders"] = [{"name": key, "count": value} for key, value in profile["namedBreeders"].most_common(5)]
        profile["topInventors"] = [{"name": key, "count": value} for key, value in profile["namedInventors"].most_common(5)]

        for key in [
            "ownerRoleCounts",
            "cropCounts",
            "jurisdictionCounts",
            "years",
        ]:
            profile[key] = dict(profile[key].most_common() if hasattr(profile[key], "most_common") else profile[key])
        profile["namedBreeders"] = [{"name": key, "count": value} for key, value in profile["namedBreeders"].most_common(20)]
        profile["namedInventors"] = [{"name": key, "count": value} for key, value in profile["namedInventors"].most_common(20)]
        for bulky_key in [
            "confidenceCounts",
            "sourceKindCounts",
            "registerCounts",
            "statusCounts",
            "years",
            "expirationBasisCounts",
            "cropCounts",
            "jurisdictionCounts",
            "expirationYears",
            "namedBreeders",
            "namedInventors",
            "sampleRecords",
        ]:
            profile.pop(bulky_key, None)
        profiles.append(profile)

    return sorted(profiles, key=lambda item: (item["sourcingScore"], item["protectedIpCount"], item["recordCount"]), reverse=True)


def write_profiles(profiles: list[dict[str, Any]]) -> None:
    owner_fields = [
        "id",
        "ownerName",
        "normalizedOwnerName",
        "companyWebsite",
        "companyDescription",
        "companySourceUrl",
        "recordCount",
        "protectedIpCount",
        "usPlantPatentCount",
        "cpvoPbrCount",
        "legalOwnerRecordCount",
        "breederSignalRecordCount",
        "inventorSignalRecordCount",
        "relevantIpRecordCount",
        "relevantLegalOwnerRecordCount",
        "firstYear",
        "lastYear",
        "recordsLast5Years",
        "filingVelocity5Year",
        "expirationNext1Year",
        "expirationNext3Years",
        "expirationNext5Years",
        "expiredProtectionCount",
        "activeProtectionCount",
        "individualOwner",
        "soleNamedBreeder",
        "cropConcentration",
        "sourcingScore",
        "sourcingFlags",
        "topCrops",
        "topJurisdictions",
        "topBreeders",
        "topInventors",
        "ownerRoleCounts",
        "annualCounts",
        "expirationSchedule",
    ]
    metadata = {
        "title": "Owner Sourcing Profiles",
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "recordCount": len(profiles),
        "methodNotes": [
            "USPTO records use assignee first, then breeder/inventor fallback.",
            "CPVO Variety Finder exports currently expose breeder names, not full holder/applicant fields, so CPVO owner profiles are breeder-signal profiles.",
            "US plant patent expiry is estimated as 20 years from filing date where filing date is available.",
            "CPVO PBR expiry is estimated as 25 years, or 30 years for tree/vine crops, from grant date when available or application date otherwise.",
        ],
    }
    rows = [[profile.get(field, "") for field in owner_fields] for profile in profiles]
    payload = {"metadata": metadata, "ownerFields": owner_fields, "owners": rows}
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def main() -> int:
    records = load_records(PATENT_PATH) + load_records(CPVO_PATH)
    profiles = build_profiles(records)
    write_profiles(profiles)
    print(f"Wrote {OUTPUT_PATH} with {len(profiles):,} owner profiles.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
