#!/usr/bin/env python3
"""Build owner-level sourcing profiles from patent and CPVO dashboard records."""

from __future__ import annotations

import datetime as dt
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CONFIG_DIR = ROOT / "config"
PATENT_PATH = DATA_DIR / "plant_patents.json"
CPVO_PATH = DATA_DIR / "cpvo_varieties.json"
OUTPUT_PATH = DATA_DIR / "owner_profiles.json"
AFFILIATION_PATH = DATA_DIR / "breeder_affiliations.json"
COMPANY_PROFILE_PATH = CONFIG_DIR / "company_profiles.json"
AUDIT_OVERRIDE_PATH = CONFIG_DIR / "company_profile_audits.json"
WEB_RESEARCH_PATHS = sorted(CONFIG_DIR.glob("profile_web_research*.json"))
PERSON_ALIAS_PATH = CONFIG_DIR / "person_name_aliases.json"
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
    "agency",
    "association",
    "university",
    "college",
    "consortium",
    "cooperative",
    "council",
    "county",
    "department",
    "development",
    "faculty",
    "federal",
    "foundation",
    "institute",
    "institut",
    "innovation",
    "laboratory",
    "ministry",
    "national",
    "organization",
    "organisation",
    "pepinieres",
    "prefecture",
    "provincial",
    "roseraies",
    "research",
    "academy",
    "government",
    "minister",
    "service",
    "station",
    "stov",
    "sociedad",
    "unipersonal",
    "usda",
    "state of",
}

LEGAL_ENTITY_PATTERN = re.compile(
    r"(?:\binc(?:orporated)?\b|\bllc\b|\bl\.?\s*l\.?\s*c\.?\b|\bltd\b|\blimited\b|"
    r"\bcorp(?:oration)?\b|\bcompany\b|\bco\.?\b|\bgmbh\b|\bb\.?\s*v\.?\b|"
    r"\bn\.?\s*v\.?\b|\bs\.?\s*a\.?\s*r\.?\s*l\.?\b|\bs\.?\s*a\.?\s*s\.?\b|"
    r"\bs\.?\s*a\.?\b|\ba\.?\s*g\.?\b|\bplc\b|\bpty\b|\bpte\b|\bllp\b|\blp\b|"
    r"\bsrl\b|\bs\.?\s*r\.?\s*l\.?\b|\bspa\b|\bs\.?\s*p\.?\s*a\.?\b|\bsro\b|"
    r"\bz\.?\s*o\.?\s*o\.?\b|\bgaec\b|\bscea\b|\bsnc\b|\bearl\b|\bkft\b|\bzrt\b|"
    r"\bholdings?\b)",
    re.I,
)

PERSON_STOPWORDS = {
    "dr",
    "prof",
    "phd",
    "ph",
    "d",
    "mr",
    "mrs",
    "ms",
    "miss",
    "jr",
    "sr",
    "ii",
    "iii",
    "iv",
    "us",
    "usa",
    "et",
    "al",
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

PROGRAM_LINEAGE_RULES = [
    {
        "canonicalName": "International Fruit Genetics",
        "pattern": re.compile(r"\bIFG(?:\b|[\s-]|\d)|\bSweet\s*(?:Celebration|Globe|Sapphire)\b", re.I),
        "fields": ["cultivar", "tradeName", "title", "primarySource"],
    },
    {
        "canonicalName": "SNFL Group",
        "pattern": re.compile(r"\bGensel\b", re.I),
        "fields": ["cultivar", "tradeName", "title", "primarySource"],
    },
    {
        "canonicalName": "Bloom Fresh International",
        "pattern": re.compile(r"\bBLOM[A-Z0-9-]*\b|\bBloom\s*Fresh\b", re.I),
        "fields": ["cultivar", "tradeName", "title", "primarySource", "breeders", "assignee"],
    },
]

NON_OWNER_NORMALIZED_NAMES = {
    "0",
    "942 0",
    "desconocido",
    "desconocido inscripci n de oficio",
    "inconnu",
    "domaine public",
    "public domain",
    "varios obtentores",
    "various breeders",
    "unknown breeder",
    "unknown owner",
    "s a",
    "s l",
    "s a s",
    "s a r l",
    "b v",
    "n v",
    "a g",
    "a s",
    "l l c",
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


def load_person_aliases() -> tuple[dict[str, str], dict[str, list[str]]]:
    if not PERSON_ALIAS_PATH.exists():
        return {}, {}
    payload = json.loads(PERSON_ALIAS_PATH.read_text(encoding="utf-8"))
    aliases: dict[str, str] = {}
    for group in payload.get("groups", []):
        canonical = clean_text(group.get("canonicalName"))
        if not canonical:
            continue
        for name in [canonical, *(group.get("aliases") or [])]:
            normalized = normalize_alias_search(name)
            if normalized:
                aliases[normalized] = canonical
    compounds: dict[str, list[str]] = {}
    for group in payload.get("compoundGroups", []):
        members = [clean_text(name) for name in group.get("members", []) if clean_text(name)]
        if len(members) < 2:
            continue
        for name in group.get("aliases", []):
            normalized = normalize_alias_search(name)
            if normalized:
                compounds[normalized] = members
    return aliases, compounds


COMPANY_PROFILES = load_company_profiles()
PERSON_NAME_ALIASES, PERSON_COMPOUND_ALIASES = load_person_aliases()


def configured_rollup_children(company: dict[str, Any]) -> list[str]:
    return [
        *[clean_text(name) for name in company.get("rollupChildren", []) if clean_text(name)],
        *[clean_text(name) for name in company.get("verifiedRollupChildren", []) if clean_text(name)],
    ]


ROLLUP_CHILD_NAMES = {
    normalize_owner_name(name)
    for company in COMPANY_PROFILES
    for name in configured_rollup_children(company)
    if normalize_owner_name(name)
}

AUDIT_FIELDS = [
    "auditStatus",
    "auditConfidence",
    "webResearchStatus",
    "webResearchReviewedAt",
    "webResearchSources",
    "webResearchNotes",
    "ownershipType",
    "ownershipSummary",
    "parentCompany",
    "headquarters",
    "leadershipSummary",
    "websiteCultivarCount",
    "websiteCultivarCountBasis",
    "websiteCultivarEvidenceUrl",
    "primaryContactName",
    "primaryContactTitle",
    "primaryContactEmail",
    "primaryContactPhone",
    "primaryContactUrl",
    "contactSourceUrl",
    "trademarkStatus",
    "trademarkOwner",
    "trademarkEvidenceUrl",
    "trademarkLastCheckedAt",
    "brandExamples",
    "auditNotes",
    "candidateParent",
    "candidateParentBasis",
    "candidateParentConfidence",
    "candidateParentEvidenceUrl",
]

AFFILIATION_FIELDS = [
    "affiliatedCompany",
    "affiliationRelationshipType",
    "affiliationIdentityConfidence",
    "affiliationConfidence",
    "affiliationStatus",
    "affiliationBasis",
    "affiliationSource",
    "affiliationDirectEvidenceCount",
    "affiliationDirectEvidenceShare",
    "affiliationRightsBasis",
    "affiliationRightsRecordIds",
    "affiliationEvidenceRecordIds",
    "affiliationEvidence",
]


def load_profile_audits() -> dict[str, dict[str, Any]]:
    audits: dict[str, dict[str, Any]] = {}
    for path in (AUDIT_OVERRIDE_PATH, *WEB_RESEARCH_PATHS):
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("profiles", payload) if isinstance(payload, dict) else payload
        for row in rows or []:
            row = dict(row)
            sources = []
            for source in row.get("webResearchSources") or []:
                if isinstance(source, dict) and clean_text(source.get("url")):
                    sources.append(source)
                elif clean_text(source):
                    sources.append({"label": "Public source", "url": clean_text(source)})
            if sources:
                row["webResearchSources"] = sources
            name = clean_text(row.get("canonicalName") or row.get("ownerName"))
            if not name:
                continue
            canonical_person = PERSON_NAME_ALIASES.get(normalize_alias_search(name), name)
            key = normalize_alias_search(canonical_person)
            audits[key] = {**audits.get(key, {}), **row}
    return audits


PROFILE_AUDITS = load_profile_audits()


def load_breeder_affiliations() -> list[dict[str, Any]]:
    if not AFFILIATION_PATH.exists():
        return []
    payload = json.loads(AFFILIATION_PATH.read_text(encoding="utf-8"))
    return payload.get("affiliations", []) if isinstance(payload, dict) else payload


def build_company_alias_index() -> list[tuple[str, str, dict[str, Any]]]:
    index: list[tuple[str, str, dict[str, Any]]] = []
    for profile in COMPANY_PROFILES:
        aliases = [profile.get("canonicalName", ""), *(profile.get("aliases") or [])]
        for alias in aliases:
            alias_normalized = normalize_alias_search(alias)
            if alias_normalized:
                index.append((alias_normalized, clean_text(alias), profile))
    return sorted(index, key=lambda item: len(item[0]), reverse=True)


COMPANY_ALIAS_INDEX = build_company_alias_index()
COMPANY_EXCLUSION_INDEX = {
    profile.get("canonicalName", ""): [
        normalized
        for normalized in (normalize_alias_search(exclusion) for exclusion in (profile.get("excludeMatches", []) or []))
        if normalized
    ]
    for profile in COMPANY_PROFILES
}


def company_profile_excluded(profile: dict[str, Any], normalized_name: str) -> bool:
    for exclusion_normalized in COMPANY_EXCLUSION_INDEX.get(profile.get("canonicalName", ""), []):
        if exclusion_normalized in normalized_name:
            return True
    return False


@lru_cache(maxsize=None)
def company_profile_for_name(name: str) -> dict[str, Any] | None:
    normalized = f" {normalize_alias_search(name)} "
    for alias_normalized, raw_alias, profile in COMPANY_ALIAS_INDEX:
        if company_profile_excluded(profile, normalized):
            continue
        if len(alias_normalized) <= 4:
            acronym_match = raw_alias.isupper() and bool(
                re.search(rf"\b{re.escape(raw_alias)}\b", clean_text(name))
            )
            if acronym_match or (not raw_alias.isupper() and f" {alias_normalized} " in normalized):
                return profile
        elif alias_normalized in normalized:
            return profile
    return None


@lru_cache(maxsize=None)
def company_profiles_for_name(name: str) -> list[dict[str, Any]]:
    normalized = f" {normalize_alias_search(name)} "
    profiles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for alias_normalized, raw_alias, profile in COMPANY_ALIAS_INDEX:
        canonical = profile["canonicalName"]
        if canonical in seen:
            continue
        if company_profile_excluded(profile, normalized):
            continue
        if len(alias_normalized) <= 4:
            matched = (
                raw_alias.isupper()
                and bool(re.search(rf"\b{re.escape(raw_alias)}\b", clean_text(name)))
            ) or (not raw_alias.isupper() and f" {alias_normalized} " in normalized)
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


def ascii_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", clean_text(value))
    return normalized.encode("ascii", "ignore").decode("ascii")


def has_legal_entity_marker(name: str) -> bool:
    return bool(LEGAL_ENTITY_PATTERN.search(ascii_key(name)))


def looks_like_address_or_location(name: str) -> bool:
    raw = ascii_key(name).strip()
    text = raw.lower()
    if normalize_owner_name(name) in {
        "ca legrand",
        "ca le grand",
        "ca us le grand",
        "le grand ca",
        "le grand ca us",
        "legrand ca",
        "legrand ca us",
        "ca us watsonville",
        "in west lafayette",
        "nj bloomsbury",
    }:
        return True
    if re.search(r"\d", text):
        return True
    if re.match(r"^(?:cerca\s+de|near|outside\s+of)\b", text):
        return True
    if re.match(r"^saint-[a-z-]+-sur-[a-z-]+$", text):
        return True
    if re.match(r"^(?:[A-Z]{2})(?:,?\s+[A-Z]{2})?\b", raw):
        return True
    if re.search(r",\s*[A-Z]{2}$", raw):
        return True
    if re.search(
        r",\s*(?:australia|belgium|brazil|canada|chile|china|france|germany|italy|"
        r"japan|mexico|netherlands|new zealand|spain|united kingdom|united states)\b",
        text,
    ):
        return True
    if re.match(
        r"^[^,]+,\s*(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|"
        r"MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|"
        r"TX|UT|VT|VA|WA|WV|WI|WY)\b",
        raw,
        flags=re.I,
    ):
        return True
    return bool(
        re.search(
            r"\b(?:road|rd|street|st|avenue|ave|highway|hwy|route|box|boulevard|blvd|"
            r"lane|ln|drive|dr|savana|postal|zip)\b",
            text,
        )
    )


def split_conjoined_people_text(part: str) -> list[str]:
    connector = r"\s+(?:and|&|y|et)\s+"
    if not re.search(connector, part, flags=re.I):
        return [part]
    if company_profile_for_name(part):
        return [part]
    normalized = normalize_owner_name(part)
    tokens = set(normalized.split())
    raw_tokens = set(re.findall(r"[a-z]+", ascii_key(part).lower()))
    legal_tokens = {re.sub(r"[^a-z]", "", term.lower()) for term in LEGAL_TERMS}
    if raw_tokens & legal_tokens or tokens & LEGAL_TERMS or tokens & INSTITUTION_TERMS:
        return [part]

    def personish(value: str) -> bool:
        if looks_like_address_or_location(value):
            return False
        words = re.findall(r"[A-Za-z]+", ascii_key(value))
        return 2 <= len([word for word in words if word.lower() not in PERSON_STOPWORDS]) <= 4

    connector_pieces = [clean_text(piece).strip(" ,") for piece in re.split(connector, part, flags=re.I)]
    pieces: list[str] = []
    for piece in connector_pieces:
        comma_pieces = [
            cleaned
            for item in piece.split(",")
            if (cleaned := clean_text(item).strip(" ,"))
        ]
        if len(comma_pieces) > 1 and all(personish(item) for item in comma_pieces):
            pieces.extend(comma_pieces)
        else:
            pieces.append(piece)
    return pieces if len(pieces) > 1 and all(personish(piece) for piece in pieces) else [part]


def split_people_or_entities(value: str) -> list[str]:
    text = clean_text(value)
    lowered = text.lower()
    if not text or lowered in {"n/a", "na", "none", "unknown"} or lowered.startswith("information not available"):
        return []
    compound = PERSON_COMPOUND_ALIASES.get(normalize_alias_search(text))
    if compound:
        return compound
    text = text.replace("\\,", ",")
    text = text.replace("^^^", "|")
    text = text.replace(" / ", "|")
    text = re.sub(r"\s*;\s*", "|", text)
    parts = []
    for part in [clean_text(part).strip(" ,") for part in text.split("|")]:
        conjoined = split_conjoined_people_text(part)
        for piece in conjoined:
            comma_pieces = [
                cleaned
                for item in piece.split(",")
                if (cleaned := clean_text(item).strip(" ,"))
            ]
            if (
                len(comma_pieces) > 1
                and all(2 <= len(person_tokens(item)) <= 4 for item in comma_pieces)
                and not any(looks_like_address_or_location(item) for item in comma_pieces)
            ):
                parts.extend(comma_pieces)
            else:
                parts.append(piece)
    return [part for part in parts if normalize_owner_name(part) not in {"n a", "na", "none", "unknown"}]


def likely_entity_name(name: str) -> bool:
    if company_profile_for_name(name):
        return True
    if has_legal_entity_marker(name):
        return True
    raw_normalized = re.sub(r"[^a-z0-9]+", " ", ascii_key(name).lower()).strip()
    if not raw_normalized:
        return False
    tokens = set(raw_normalized.split())
    if any(term in raw_normalized for term in INSTITUTION_TERMS if " " in term):
        return True
    if tokens & INSTITUTION_TERMS:
        return True
    entity_terms = {
        "breeding",
        "cultivar",
        "cultivars",
        "genetics",
        "nursery",
        "plant",
        "plants",
        "research",
        "seed",
        "seeds",
        "foundation",
        "program",
        "station",
        "department",
        "division",
        "center",
        "centre",
        "association",
        "group",
        "farm",
        "farms",
        "fresh",
        "fruit",
        "fruits",
        "berry",
        "berries",
    }
    return bool(tokens & entity_terms)


def person_tokens(name: str) -> list[str]:
    text = ascii_key(name)
    text = re.sub(r"\([^)]*\)", " ", text)
    text = text.replace("_", " ")
    text = re.sub(r"\b(?:et\s+al|and\s+others)\b", " ", text, flags=re.I)
    text = re.sub(r"['`]", "", text)
    text = re.sub(r"[^A-Za-z]+", " ", text).lower().strip()
    tokens = [token for token in text.split() if token not in PERSON_STOPWORDS]
    return tokens


def person_keys(name: str) -> list[str]:
    if likely_entity_name(name):
        return []
    text = clean_text(name)
    tokens = person_tokens(text)
    if len(tokens) < 2 or len(tokens) > 4:
        return []
    if "," in text:
        key = f"{tokens[-1]} {tokens[0]}"
        return [key]
    first = tokens[0]
    last = tokens[-1]
    first_last = f"{first} {last}"
    last_first = f"{last} {first}"
    initial_last = f"{first[0]} {last}" if first else ""
    last_initial = f"{last} {first[0]}" if first else ""
    return [
        key
        for key in dict.fromkeys([first_last, last_first, initial_last, last_initial])
        if key.strip()
    ]


def display_person_name(name: str) -> str:
    text = clean_text(name)
    text = re.sub(r"\([^)]*\)", " ", text)
    text = text.replace("_", " ")
    text = re.sub(r"\b(?:et\s+al|and\s+others)\b", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" ,")
    if "," in text:
        parts = [part.strip() for part in text.split(",", 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            text = f"{parts[1]} {parts[0]}"
    else:
        raw_words = text.split()
        if (
            len(raw_words) == 3
            and len(raw_words[2].strip(".")) == 1
            and len(raw_words[1].strip(".")) > 1
        ):
            text = f"{raw_words[1]} {raw_words[2]} {raw_words[0]}"
    words = []
    for word in text.split():
        if len(word) == 1:
            words.append(f"{word.upper()}.")
        elif word.isupper():
            words.append(word.title())
        else:
            words.append(word)
    return " ".join(words).replace("..", ".")


def person_display_score(name: str, count: int) -> int:
    text = clean_text(name)
    score = count
    if re.search(r"\b[A-Z]\.\s*[A-Z][A-Za-z-]+$", text):
        score += 15
    if "," in text:
        score -= 8
    if "_" in text:
        score -= 8
    if text.isupper():
        score -= 12
    if re.search(r"\bet\s+al\b", text, re.I):
        score -= 20
    if len(person_tokens(text)) == 2:
        score += 2
    return score


def build_name_alias_map(records: list[dict[str, Any]]) -> dict[str, str]:
    counts: Counter[str] = Counter()
    key_to_names: dict[str, Counter[str]] = defaultdict(Counter)
    for row in records:
        for field in ("breeders", "inventors"):
            for raw_name in split_people_or_entities(row.get(field, "")):
                if looks_like_address_or_location(raw_name):
                    continue
                company_profile = company_profile_for_name(raw_name)
                if company_profile:
                    display = company_profile["canonicalName"]
                    key_to_names[f"entity:{normalize_owner_name(display)}"][display] += 1
                    continue
                override = PERSON_NAME_ALIASES.get(normalize_alias_search(raw_name))
                display_source = override or raw_name
                keys = person_keys(display_source)
                if not keys:
                    display = display_owner_name(raw_name)
                    key_to_names[f"entity:{normalize_owner_name(display)}"][display] += 1
                    continue
                display = override or display_person_name(raw_name)
                counts[display] += 1
                for key in keys:
                    key_to_names[f"person:{key}"][display] += 1

    alias_choices: dict[str, tuple[str, int]] = {}
    for names in key_to_names.values():
        if not names:
            continue
        best = max(names, key=lambda name: (person_display_score(name, names[name]), names[name], -len(name)))
        best_score = person_display_score(best, names[best])
        for name in names:
            key = normalize_owner_name(name)
            current = alias_choices.get(key)
            if not current or best_score > current[1]:
                alias_choices[key] = (best, best_score)
    return {key: value for key, (value, _score) in alias_choices.items()}


def canonical_named_party(name: str, alias_map: dict[str, str]) -> str:
    if looks_like_address_or_location(name):
        return ""
    person_parts = person_tokens(name)
    if person_parts and all(len(part) == 1 for part in person_parts):
        return ""
    company_profile = company_profile_for_name(name)
    if company_profile:
        return company_profile["canonicalName"]
    override = PERSON_NAME_ALIASES.get(normalize_alias_search(name))
    if override:
        return override
    display = display_person_name(name) if person_keys(name) else display_owner_name(name)
    return alias_map.get(normalize_owner_name(display), display)


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


def owner_candidates(row: dict[str, Any], alias_map: dict[str, str]) -> list[tuple[str, str, str]]:
    candidates: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    def add_candidate(name: str, role: str, confidence: str) -> None:
        name = canonical_named_party(name, alias_map)
        key = normalize_owner_name(display_owner_name(name))
        if not key or key in seen or key in NON_OWNER_NORMALIZED_NAMES:
            return
        seen.add(key)
        candidates.append((name, role, confidence))

    def add_from_value(value: str, role: str, confidence: str) -> None:
        for name in split_people_or_entities(value):
            company_profiles = company_profiles_for_name(name)
            names = [profile["canonicalName"] for profile in company_profiles] or [name]
            for expanded_name in names:
                add_candidate(expanded_name, role, confidence)

    def add_program_lineage() -> None:
        for rule in PROGRAM_LINEAGE_RULES:
            haystack = " ".join(clean_text(row.get(field)) for field in rule["fields"])
            if rule["pattern"].search(haystack):
                add_candidate(rule["canonicalName"], "Program lineage", "medium")

    if is_cpvo(row):
        add_from_value(row.get("breeders", ""), "CPVO breeder", "medium")
    else:
        add_from_value(row.get("assignee", ""), "Patent assignee", "high")
        if not candidates:
            add_from_value(row.get("breeders", ""), "Breeder", "medium")
        if not candidates:
            add_from_value(row.get("inventors", ""), "Inventor", "low")
    add_program_lineage()
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
    if looks_like_address_or_location(name) or likely_entity_name(name):
        return False
    if re.search(r"(?:&\.|-\.)", clean_text(name)):
        return False
    words = person_tokens(name)
    return 2 <= len(words) <= 4


def owner_id(normalized_name: str) -> str:
    import hashlib

    return "OWNER-" + hashlib.sha1(normalized_name.encode("utf-8")).hexdigest()[:12].upper()


def score_profile(profile: dict[str, Any]) -> tuple[int, list[str]]:
    record_count = profile["recordCount"]
    protected_count = profile["protectedIpCount"]
    legal_owner_count = profile["legalOwnerRecordCount"]
    relevant_count = profile["relevantIpRecordCount"]
    jurisdictions = len(profile.get("jurisdictionCounts") or profile.get("topJurisdictions") or [])
    latest_year = profile.get("lastYear") or 0
    recency = max(0, min(20, latest_year - 2006)) if latest_year else 0
    scale = min(25, math.log1p(max(record_count, relevant_count)) * 4.5)
    protected = min(20, protected_count / max(1, record_count) * 20)
    jurisdiction_score = min(12, jurisdictions * 2.5)
    velocity = min(12, profile["recordsLast5Years"] * 1.2)
    durability = min(8, profile["activeProtectionCount"] / max(1, protected_count) * 8) if protected_count else 0
    crop_names = list((profile.get("cropCounts") or {}).keys()) or [item.get("crop", "") for item in profile.get("topCrops", [])]
    crop_score = max((CROP_ATTRACTIVENESS.get(crop.lower(), 5) for crop in crop_names), default=5)
    legal_confidence = min(12, legal_owner_count * 1.2)
    relevance = min(10, relevant_count * 0.8)
    score = round(scale + protected + jurisdiction_score + velocity + durability + crop_score + legal_confidence + relevance + recency * 0.35)

    flags: list[str] = []
    if profile.get("isParentRollup"):
        flags.append("Parent-company rollup")
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


def institutional_or_public_signal(profile: dict[str, Any]) -> bool:
    scale_class = clean_text(profile.get("acquisitionScaleClass")).lower()
    if scale_class == "public_institution":
        return True
    if scale_class in {
        "small_private_override",
        "scale_verification_required",
        "private_consortium",
        "strategic_scale",
    }:
        return False
    text = normalize_owner_name(
        " ".join(
            [
                clean_text(profile.get("ownerName")),
                clean_text(profile.get("targetFit")),
                clean_text(profile.get("ownershipType")),
                clean_text(profile.get("parentCompany")),
            ]
        )
    )
    public_terms = {
        "public",
        "university",
        "usda",
        "government",
        "department",
        "institute",
        "institut",
        "research",
        "state",
        "foundation seed",
        "agricultural research",
    }
    tokens = set(text.split())
    return any((term in text) if " " in term else (term in tokens) for term in public_terms)


def large_platform_signal(profile: dict[str, Any]) -> bool:
    scale_class = clean_text(profile.get("acquisitionScaleClass")).lower()
    target_fit = clean_text(profile.get("targetFit")).lower()
    ownership_text = " ".join(
        clean_text(profile.get(field)).lower()
        for field in ("ownershipType", "ownershipSummary", "parentCompany")
    )
    if any(
        phrase in target_fit
        for phrase in (
            "far too large",
            "too large",
            "benchmark only",
            "benchmark platform",
            "larger than the current target range",
            "above the current target range",
            "already institutionally owned",
            "above the target size range",
            "not a straightforward acquisition target",
            "strategic benchmark",
            "acquired by planasa",
        )
    ):
        return True
    if any(
        phrase in ownership_text
        for phrase in (
            "strategic-scale",
            "strategic platform",
            "grower-owned cooperative",
            "member-owned cooperative",
            "ew group-owned",
            "grupo samca",
            "naturipe",
            "simplot investment",
        )
    ):
        return True
    if scale_class == "small_private_override":
        return False
    if scale_class == "strategic_scale":
        return True
    return int(profile.get("recordCount") or 0) > 400 or int(profile.get("protectedIpCount") or 0) > 200


def non_control_structure_signal(profile: dict[str, Any]) -> bool:
    text = " ".join(
        clean_text(profile.get(field)).lower()
        for field in ("targetFit", "ownershipType", "ownershipSummary")
    )
    return any(
        phrase in text
        for phrase in (
            "grower-member",
            "member-owned",
            "cooperative",
            "consortium",
            "jointly controlled",
            "licensing vehicle",
            "breeding association",
            "commercialization partnership",
            "licensing opportunity rather than",
            "licensing target rather than",
            "partnership/licensing target",
        )
    )


def score_acquisition_fit(profile: dict[str, Any]) -> tuple[int, str, list[str], list[str]]:
    """Rank how actionable a profile looks for the $1-5m EBITDA acquisition screen."""
    record_count = int(profile.get("recordCount") or 0)
    protected_count = int(profile.get("protectedIpCount") or 0)
    relevant_count = int(profile.get("relevantIpRecordCount") or 0)
    legal_owner_count = int(profile.get("legalOwnerRecordCount") or 0)
    active_count = int(profile.get("activeProtectionCount") or 0)
    expiration_next_5 = int(profile.get("expirationNext5Years") or 0)
    records_last_5 = int(profile.get("recordsLast5Years") or 0)
    velocity = float(profile.get("filingVelocity5Year") or 0)
    crop_concentration = float(profile.get("cropConcentration") or 0)
    jurisdiction_count = len(profile.get("topJurisdictions") or [])
    brand_examples = profile.get("brandExamples") or []
    if isinstance(brand_examples, str):
        brand_examples = [item.strip() for item in brand_examples.split("|") if item.strip()]
    has_contact = bool(
        clean_text(profile.get("companyContactUrl"))
        or clean_text(profile.get("primaryContactUrl"))
        or clean_text(profile.get("contactSourceUrl"))
    )
    has_profile = bool(clean_text(profile.get("companyWebsite")) or clean_text(profile.get("companyDescription")))
    has_cultivar_evidence = bool(clean_text(profile.get("websiteCultivarEvidenceUrl")))
    has_news = bool(profile.get("companyNewsLinks"))
    audit_confidence = clean_text(profile.get("auditConfidence")).lower()
    web_research_status = clean_text(profile.get("webResearchStatus")).lower()
    ownership_type = clean_text(profile.get("ownershipType")).lower()
    trademark_status = clean_text(profile.get("trademarkStatus")).lower()
    is_public = institutional_or_public_signal(profile)
    is_large = large_platform_signal(profile)
    is_non_control = non_control_structure_signal(profile)
    scale_class = clean_text(profile.get("acquisitionScaleClass")).lower()
    scale_verification_required = scale_class == "scale_verification_required"
    resolved_affiliation = clean_text(profile.get("affiliationStatus")) in {
        "verified_relationship",
        "probable_relationship",
    }
    unresolved_identity = (
        web_research_status in {"unresolved", "identity_unresolved"}
        or "identity unresolved" in ownership_type
    )
    suppress_scoring = "suppress_scoring" in web_research_status or unresolved_identity
    not_actionable = web_research_status.startswith("not_actionable")
    identity_rebuild_required = any(
        marker in web_research_status
        for marker in (
            "wrong_domain",
            "record_split_required",
            "identity_unresolved",
            "legal_name_mismatch",
        )
    )
    ownership_verification_required = (
        "current_parent_medium" in web_research_status
        or "institutional ownership history" in clean_text(profile.get("ownershipType")).lower()
        or "current ultimate ownership requires" in clean_text(profile.get("targetFit")).lower()
    )
    rights_holder_verification_required = (
        relevant_count > 0
        and legal_owner_count == 0
        and not profile.get("individualOwner")
    )

    score = 0
    reasons: list[str] = []
    blockers: list[str] = []

    # 1. Right-sized portfolio: enough IP to matter, not so much it is a strategic-scale platform.
    if relevant_count:
        reasons.append("Relevant fruit, tree nut, or vegetable IP exposure")
    else:
        blockers.append("No relevant fruit, tree nut, or vegetable exposure")

    if scale_class == "small_private_override" and relevant_count:
        score += 12
        reasons.append("Operating company appears small despite duplicated or multi-jurisdiction record volume")
        blockers.append("Portfolio counts require legal-holder and duplicate-right reconciliation")
    elif 5 <= relevant_count <= 100 and 3 <= protected_count <= 60 and record_count <= 150:
        score += 20
        reasons.append("Right-sized protected portfolio")
    elif 2 <= relevant_count <= 150 and 1 <= protected_count <= 100 and record_count <= 250:
        score += 14
        reasons.append("Portfolio size may be diligenceable")
    elif 1 <= relevant_count and protected_count <= 150 and record_count <= 300:
        score += 7
        reasons.append("Relevant but less ideally sized portfolio")
    elif protected_count > 150 or record_count > 300:
        blockers.append("Portfolio scale is likely too large for the current target range")
    else:
        blockers.append("Portfolio may be too thin to underwrite")

    # 2. Focused crop mix: specialized crop programs are easier to understand and diligence.
    if crop_concentration >= 0.75 and relevant_count >= 5:
        score += 15
        reasons.append("Focused crop mix")
    elif crop_concentration >= 0.5:
        score += 10
        reasons.append("Moderately focused crop mix")
    elif record_count >= 10:
        score += 4
        reasons.append("Diversified crop mix")

    # 3. Royalty durability: active rights, manageable cliffs, and global coverage support royalty value.
    if protected_count and active_count:
        active_ratio = active_count / max(1, protected_count)
        cliff_share = expiration_next_5 / max(1, protected_count)
        if active_ratio >= 0.75 and cliff_share <= 0.25:
            score += 14
            reasons.append("Active protection with limited five-year cliff")
        elif active_ratio >= 0.5 and cliff_share <= 0.5:
            score += 9
            reasons.append("Moderate protection durability")
        elif expiration_next_5 >= 2:
            score += 4
            reasons.append("Near-term expiration cliff may create royalty-pressure angle")
        if jurisdiction_count >= 3:
            score += 4
            reasons.append("Multi-jurisdiction protection signal")
        if "live" in trademark_status or "registered" in trademark_status:
            score += 2
            reasons.append("Registered or live trademark signal")
        elif brand_examples:
            score += 1
            reasons.append("Brand names captured; trademark status still needs verification")
    elif protected_count:
        score += 4
        blockers.append("Protected IP present, but active/expired status is incomplete")

    # 4. Private / acquirable ownership: favor private or individual holders over institutions.
    if is_public:
        blockers.append("Public, university, government, or research-institution signal")
    elif profile.get("individualOwner") and not resolved_affiliation:
        score += 15
        reasons.append("Individual-owner or succession signal")
    elif resolved_affiliation:
        score += 2
        blockers.append("Individual is affiliated with a company or breeding program; target the rights holder separately")
    elif has_profile:
        score += 12
        reasons.append("Private or company-level profile signal")
    else:
        score += 4
        blockers.append("No verified company profile captured")

    # 5. Recent activity without being institutional scale.
    if records_last_5 >= 8 or velocity >= 1.5:
        score += 10
        reasons.append("Recent filing activity")
    elif records_last_5 > 0:
        score += 6
        reasons.append("Some recent activity")
    elif record_count >= 5:
        blockers.append("Dormant filing pattern")

    # 6. Commercial validation: public cultivar pages and contact paths make a target actionable.
    commercial = 0
    if has_profile:
        commercial += 3
    if has_cultivar_evidence:
        commercial += 3
    if has_news:
        commercial += 2
    if has_contact:
        commercial += 2
    score += min(10, commercial)
    if commercial >= 6:
        reasons.append("Commercial validation links captured")
    elif has_profile:
        blockers.append("Company profile exists but commercial evidence is still thin")
    else:
        blockers.append("No public commercial validation captured")

    # 7. Succession / relationship signal.
    if (profile.get("individualOwner") or profile.get("soleNamedBreeder")) and not resolved_affiliation:
        score += 5
        reasons.append("Succession or thin-bench signal")
    elif int(profile.get("breederSignalRecordCount") or 0) and not legal_owner_count:
        score += 2
        blockers.append("Breeder-signal profile needs holder confirmation")

    # 8. Data confidence: do not over-rank low-confidence profiles.
    data_confidence = 0
    if audit_confidence == "high":
        data_confidence += 3
    elif audit_confidence == "medium":
        data_confidence += 2
    if legal_owner_count:
        data_confidence += 1
    if has_contact or clean_text(profile.get("companyWebsite")):
        data_confidence += 1
    if "verified" in web_research_status and "unresolved" not in web_research_status:
        data_confidence += 1 if "record_split_required" in web_research_status else 2
    if "record_split_required" in web_research_status:
        blockers.append("Record-level owner split is required before consolidation")
    score += min(5, data_confidence)
    if data_confidence >= 4:
        reasons.append("Higher data-confidence profile")
    if not legal_owner_count and not profile.get("individualOwner"):
        blockers.append("No confirmed legal-owner records")
    if not has_contact:
        blockers.append("No source-backed contact path captured")

    if is_large:
        score -= 45
        blockers.append("Benchmark-scale or institutionally owned platform")
    if is_public:
        score -= 30
    if is_non_control and not is_large and not is_public:
        score -= 20
        blockers.append("Association, partnership, or non-control structure may limit acquisition feasibility")
    if scale_verification_required and not is_large and not is_public:
        score -= 15
        blockers.append("Operating scale may exceed the target range and needs financial verification")
    if suppress_scoring:
        score -= 50
        blockers.append("Identity cannot be matched to a unique breeder or owner")
    elif not_actionable:
        score -= 45
        blockers.append("Verified as a strategic, public, acquired, or otherwise non-actionable profile")
    elif identity_rebuild_required:
        score -= 10
        blockers.append("Company identity or record ownership needs reconstruction")
    elif ownership_verification_required:
        score -= 10
        blockers.append("Current parent or ultimate ownership needs confirmation")

    score = max(0, min(100, round(score)))
    if is_large:
        score = min(score, 30)
        band = "Benchmark / too large"
    elif is_public:
        score = min(score, 45)
        band = "Public / institutional"
    elif suppress_scoring:
        score = min(score, 25)
        band = "Identity unresolved"
    elif not_actionable:
        score = min(score, 30)
        band = "Benchmark / not actionable"
    elif is_non_control:
        score = min(score, 50)
        band = "Partnership / non-control"
    elif identity_rebuild_required:
        score = min(score, 60)
        band = "Identity verification needed"
    elif ownership_verification_required:
        score = min(score, 65)
        band = "Ownership verification needed"
    elif scale_verification_required:
        score = min(score, 70)
        band = "Scale verification needed"
    elif rights_holder_verification_required:
        score = min(score, 70)
        band = "Rights-holder verification needed"
    elif resolved_affiliation and (profile.get("individualOwner") or profile.get("soleNamedBreeder")):
        score = min(score, 40)
        band = "Affiliated breeder / company target"
    elif (
        (profile.get("individualOwner") or profile.get("soleNamedBreeder"))
        and not has_profile
        and not legal_owner_count
        and not web_research_status
    ):
        score = min(score, 50)
        band = "Affiliation research needed"
    elif (profile.get("individualOwner") or profile.get("soleNamedBreeder")) and not has_profile and not legal_owner_count:
        score = min(score, 70)
        band = "Succession lead / verify owner"
    elif not clean_text(profile.get("companyWebsite")):
        score = min(score, 70)
        band = "Needs website verification"
    elif not has_profile and not profile.get("individualOwner"):
        score = min(score, 65)
        band = "Needs verification"
    elif score >= 75:
        band = "High-fit"
    elif score >= 55:
        band = "Review"
    elif score >= 35:
        band = "Research"
    else:
        band = "Low-fit"

    return score, band, reasons[:6], blockers[:6]


def apply_acquisition_scores(profiles: list[dict[str, Any]]) -> None:
    for profile in profiles:
        score, band, reasons, blockers = score_acquisition_fit(profile)
        profile["acquisitionFitScore"] = score
        profile["acquisitionFitBand"] = band
        profile["acquisitionFitReasons"] = reasons
        profile["acquisitionFitBlockers"] = blockers


def merge_counter_lists(children: list[dict[str, Any]], field: str, label_key: str) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for child in children:
        for item in child.get(field, []) or []:
            label = clean_text(item.get(label_key))
            if label:
                counter[label] += int(item.get("count") or 0)
    return [{label_key: key, "count": value} for key, value in counter.most_common(8)]


def merge_year_lists(children: list[dict[str, Any]], field: str) -> list[dict[str, int]]:
    counter: Counter[int] = Counter()
    for child in children:
        for item in child.get(field, []) or []:
            try:
                year = int(item.get("year"))
            except (TypeError, ValueError):
                continue
            counter[year] += int(item.get("count") or 0)
    return [{"year": year, "count": counter[year]} for year in sorted(counter)]


def unique_names(names: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for name in names:
        cleaned = clean_text(name)
        normalized = normalize_owner_name(cleaned)
        if not cleaned or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(cleaned)
    return unique


def summarize_rollup_records(
    children: list[dict[str, Any]],
    record_index: dict[str, dict[str, Any]],
    alias_map: dict[str, str],
) -> dict[str, Any]:
    record_ids: set[str] = set()
    record_roles: dict[str, set[str]] = defaultdict(set)
    for child in children:
        for record_id in child.get("_recordIds", set()):
            record_ids.add(record_id)
            record_roles[record_id].update(child.get("_recordRoles", {}).get(record_id, set()))

    role_counts: Counter[str] = Counter()
    crop_counts: Counter[str] = Counter()
    jurisdiction_counts: Counter[str] = Counter()
    breeder_counts: Counter[str] = Counter()
    inventor_counts: Counter[str] = Counter()
    cultivar_labels: set[str] = set()
    annual_counts: Counter[int] = Counter()
    expiration_counts: Counter[int] = Counter()
    owner_scoped_annual_counts: Counter[int] = Counter()
    owner_scoped_expiration_counts: Counter[int] = Counter()
    metrics = Counter()

    for record_id in record_ids:
        row = record_index.get(record_id)
        if not row:
            continue
        roles = record_roles.get(record_id, set())
        for role in roles:
            role_counts[role] += 1
        if "Patent assignee" in roles:
            metrics["legalOwnerRecordCount"] += 1
            metrics["ownerScopedRecordCount"] += 1
        if roles & {"CPVO breeder", "Breeder"}:
            metrics["breederSignalRecordCount"] += 1
        if "Inventor" in roles:
            metrics["inventorSignalRecordCount"] += 1

        relevant_crop = is_relevant_sourcing_crop(row)
        if relevant_crop:
            metrics["relevantIpRecordCount"] += 1
            if "Patent assignee" in roles:
                metrics["relevantLegalOwnerRecordCount"] += 1
                metrics["ownerScopedRelevantRecordCount"] += 1

        crop_counts[clean_text(row.get("crop")) or "Unclassified"] += 1
        jurisdiction_counts[jurisdiction(row)] += 1
        cultivar_label = clean_text(row.get("cultivar") or row.get("title")).lower()
        if cultivar_label:
            cultivar_labels.add(cultivar_label)
        year = record_year(row)
        if year:
            annual_counts[year] += 1
            if "Patent assignee" in roles:
                owner_scoped_annual_counts[year] += 1

        for breeder in {
            canonical_named_party(name, alias_map)
            for name in split_people_or_entities(row.get("breeders", ""))
        } - {""}:
            breeder_counts[breeder] += 1
        for inventor in {
            canonical_named_party(name, alias_map)
            for name in split_people_or_entities(row.get("inventors", ""))
        } - {""}:
            inventor_counts[inventor] += 1

        source_kind = clean_text(row.get("sourceKind")).lower()
        protected = is_us_plant_patent(row) or (
            "plant breeders" in source_kind and clean_text(row.get("registerType")).upper() == "PBR"
        )
        if not protected:
            continue
        metrics["protectedIpCount"] += 1
        owner_scoped = "Patent assignee" in roles
        if owner_scoped:
            metrics["ownerScopedProtectedIpCount"] += 1
        if is_us_plant_patent(row):
            metrics["usPlantPatentCount"] += 1
        if is_cpvo(row) and clean_text(row.get("registerType")).upper() == "PBR":
            metrics["cpvoPbrCount"] += 1
        expiration_text, _basis = expiration_date(row)
        expiration = parse_date(expiration_text)
        if not expiration:
            continue
        expiration_counts[expiration.year] += 1
        if owner_scoped:
            owner_scoped_expiration_counts[expiration.year] += 1
        if expiration < TODAY:
            metrics["expiredProtectionCount"] += 1
            if owner_scoped:
                metrics["ownerScopedExpiredProtectionCount"] += 1
            continue
        metrics["activeProtectionCount"] += 1
        if owner_scoped:
            metrics["ownerScopedActiveProtectionCount"] += 1
        days = (expiration - TODAY).days
        if days <= 365:
            metrics["expirationNext1Year"] += 1
            if owner_scoped:
                metrics["ownerScopedExpirationNext1Year"] += 1
        if days <= 365 * 3:
            metrics["expirationNext3Years"] += 1
            if owner_scoped:
                metrics["ownerScopedExpirationNext3Years"] += 1
        if days <= 365 * 5:
            metrics["expirationNext5Years"] += 1
            if owner_scoped:
                metrics["ownerScopedExpirationNext5Years"] += 1

    years = sorted(annual_counts)
    current_year = TODAY.year
    records_last_5_years = sum(count for year, count in annual_counts.items() if year >= current_year - 4)
    top_crop_count = max(crop_counts.values(), default=0)
    return {
        "recordCount": len(record_ids),
        "distinctCultivarCount": len(cultivar_labels),
        "protectedIpCount": metrics["protectedIpCount"],
        "usPlantPatentCount": metrics["usPlantPatentCount"],
        "cpvoPbrCount": metrics["cpvoPbrCount"],
        "legalOwnerRecordCount": metrics["legalOwnerRecordCount"],
        "breederSignalRecordCount": metrics["breederSignalRecordCount"],
        "inventorSignalRecordCount": metrics["inventorSignalRecordCount"],
        "relevantIpRecordCount": metrics["relevantIpRecordCount"],
        "relevantLegalOwnerRecordCount": metrics["relevantLegalOwnerRecordCount"],
        "ownerScopedRecordCount": metrics["ownerScopedRecordCount"],
        "ownerScopedRelevantRecordCount": metrics["ownerScopedRelevantRecordCount"],
        "ownerScopedProtectedIpCount": metrics["ownerScopedProtectedIpCount"],
        "ownerScopedActiveProtectionCount": metrics["ownerScopedActiveProtectionCount"],
        "ownerScopedExpiredProtectionCount": metrics["ownerScopedExpiredProtectionCount"],
        "ownerScopedExpirationNext1Year": metrics["ownerScopedExpirationNext1Year"],
        "ownerScopedExpirationNext3Years": metrics["ownerScopedExpirationNext3Years"],
        "ownerScopedExpirationNext5Years": metrics["ownerScopedExpirationNext5Years"],
        "firstYear": years[0] if years else None,
        "lastYear": years[-1] if years else None,
        "recordsLast5Years": records_last_5_years,
        "filingVelocity5Year": round(records_last_5_years / 5, 2),
        "expirationNext1Year": metrics["expirationNext1Year"],
        "expirationNext3Years": metrics["expirationNext3Years"],
        "expirationNext5Years": metrics["expirationNext5Years"],
        "expiredProtectionCount": metrics["expiredProtectionCount"],
        "activeProtectionCount": metrics["activeProtectionCount"],
        "cropConcentration": round(top_crop_count / max(1, len(record_ids)), 3),
        "topCrops": [{"crop": key, "count": value} for key, value in crop_counts.most_common(8)],
        "topJurisdictions": [
            {"jurisdiction": key, "count": value} for key, value in jurisdiction_counts.most_common(8)
        ],
        "topBreeders": [{"name": key, "count": value} for key, value in breeder_counts.most_common(8)],
        "topInventors": [{"name": key, "count": value} for key, value in inventor_counts.most_common(8)],
        "ownerRoleCounts": dict(role_counts),
        "annualCounts": [{"year": year, "count": annual_counts[year]} for year in years],
        "ownerScopedAnnualCounts": [
            {"year": year, "count": owner_scoped_annual_counts[year]}
            for year in sorted(owner_scoped_annual_counts)
        ],
        "expirationSchedule": [
            {"year": year, "count": expiration_counts[year]} for year in sorted(expiration_counts)
        ],
        "ownerScopedExpirationSchedule": [
            {"year": year, "count": owner_scoped_expiration_counts[year]}
            for year in sorted(owner_scoped_expiration_counts)
        ],
        "_recordIds": record_ids,
        "_recordRoles": record_roles,
    }


def add_parent_rollups(
    profiles: list[dict[str, Any]],
    record_index: dict[str, dict[str, Any]],
    alias_map: dict[str, str],
) -> list[dict[str, Any]]:
    by_owner = {profile["ownerName"]: profile for profile in profiles}
    by_normalized = {profile["normalizedOwnerName"]: profile for profile in profiles}
    output = list(profiles)
    absorbed_normalized: set[str] = set()
    for company in COMPANY_PROFILES:
        normalized = normalize_owner_name(company["canonicalName"])
        if normalized in absorbed_normalized:
            continue
        existing_parent = by_normalized.get(normalized)
        children = [
            by_owner[name]
            for name in configured_rollup_children(company)
            if name in by_owner and not by_owner[name].get("individualOwner")
        ]
        # A display suppression is safe only when another configured rollup retains
        # the source records. Unpaired suppressions remain visible in the census.
        suppressed_names = [
            clean_text(name)
            for name in company.get("suppressProfiles", [])
            if clean_text(name)
            and normalize_owner_name(name) in ROLLUP_CHILD_NAMES
            and not by_normalized.get(normalize_owner_name(name), {}).get("individualOwner")
        ]
        if not children and not existing_parent and not suppressed_names:
            continue
        rollup_parts = []
        if existing_parent:
            rollup_parts.append(existing_parent)
        rollup_parts.extend(child for child in children if child.get("normalizedOwnerName") != normalized)
        if not rollup_parts:
            continue
        suppressed_normalized = {
            normalized,
            *(child.get("normalizedOwnerName") for child in children),
            *(normalize_owner_name(name) for name in suppressed_names),
        }
        absorbed_normalized.update(item for item in suppressed_normalized if item != normalized)
        output = [
            profile
            for profile in output
            if profile.get("normalizedOwnerName") not in suppressed_normalized
        ]
        rollup = {
            "id": owner_id(normalized),
            "ownerName": company["canonicalName"],
            "normalizedOwnerName": normalized,
            "companyWebsite": company.get("website", ""),
            "companyDescription": company.get("description", ""),
            "companySourceUrl": company.get("sourceUrl", ""),
            "companyContactUrl": company.get("contactUrl", ""),
            "companyLinkedInUrl": company.get("linkedinUrl", ""),
            "companyNewsLinks": company.get("newsLinks", []),
            "targetFit": company.get("targetFit", ""),
            "acquisitionScaleClass": company.get("acquisitionScaleClass", ""),
            "individualOwner": False,
            "soleNamedBreeder": False,
            "isParentRollup": True,
            "rollupChildren": unique_names([
                *[child["ownerName"] for child in rollup_parts if child["ownerName"] != company["canonicalName"]],
                *suppressed_names,
            ]),
        }
        rollup.update(summarize_rollup_records(rollup_parts, record_index, alias_map))
        score, flags = score_profile(rollup)
        rollup["sourcingScore"] = score
        rollup["sourcingFlags"] = flags
        output.append(rollup)
    return output


def apply_profile_audits(profiles: list[dict[str, Any]]) -> None:
    for profile in profiles:
        audit = PROFILE_AUDITS.get(normalize_alias_search(profile.get("ownerName", "")))
        for field in AUDIT_FIELDS:
            profile[field] = audit.get(field, "") if audit else ""
        official_website = clean_text(audit.get("officialWebsite")) if audit else ""
        if official_website and not clean_text(profile.get("companyWebsite")):
            profile["companyWebsite"] = official_website


def apply_breeder_affiliations(
    profiles: list[dict[str, Any]],
    affiliations: list[dict[str, Any]] | None = None,
) -> None:
    """Attach relationship evidence without transferring portfolio ownership."""
    rows = affiliations if affiliations is not None else load_breeder_affiliations()
    by_id = {clean_text(profile.get("id")): profile for profile in profiles}
    by_normalized = {
        clean_text(profile.get("normalizedOwnerName")): profile
        for profile in profiles
        if clean_text(profile.get("normalizedOwnerName"))
    }
    for profile in profiles:
        for field in AFFILIATION_FIELDS:
            profile[field] = [] if field in {
                "affiliationRightsRecordIds",
                "affiliationEvidenceRecordIds",
                "affiliationEvidence",
            } else ""
        profile["affiliatedBreederCount"] = 0
        profile["affiliatedBreeders"] = []

    confidence_rank = {"high": 3, "medium": 2, "low": 1, "unverified": 0}
    company_breeders: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        breeder_profile = by_id.get(clean_text(row.get("breederId")))
        if not breeder_profile:
            breeder_profile = by_normalized.get(clean_text(row.get("normalizedBreederName")))
        if breeder_profile:
            values = {
                "affiliatedCompany": row.get("companyName", ""),
                "affiliationRelationshipType": row.get("relationshipType", ""),
                "affiliationIdentityConfidence": row.get("identityConfidence", ""),
                "affiliationConfidence": row.get("relationshipConfidence", ""),
                "affiliationStatus": row.get("status", ""),
                "affiliationBasis": row.get("basis", ""),
                "affiliationSource": row.get("source", ""),
                "affiliationDirectEvidenceCount": row.get("directEvidenceCount", 0),
                "affiliationDirectEvidenceShare": row.get("directEvidenceShare", 0),
                "affiliationRightsBasis": row.get("rightsBasis", "none"),
                "affiliationRightsRecordIds": row.get("rightsRecordIds", []),
                "affiliationEvidenceRecordIds": row.get("evidenceRecordIds", []),
                "affiliationEvidence": row.get("evidence", []),
            }
            breeder_profile.update(values)

        if row.get("status") not in {"verified_relationship", "probable_relationship"}:
            continue
        company_name = canonical_owner_name(clean_text(row.get("companyName")))
        company_normalized = normalize_owner_name(company_name)
        if not company_normalized:
            continue
        company_breeders[company_normalized].append(
            {
                "name": clean_text(row.get("breederName")),
                "relationshipType": clean_text(row.get("relationshipType")),
                "confidence": clean_text(row.get("relationshipConfidence")),
                "status": clean_text(row.get("status")),
                "basis": clean_text(row.get("basis")),
                "rightsBasis": clean_text(row.get("rightsBasis")) or "none",
                "rightsRecordCount": len(row.get("rightsRecordIds") or []),
            }
        )

    for company_normalized, breeders in company_breeders.items():
        company_profile = by_normalized.get(company_normalized)
        if not company_profile:
            continue
        deduplicated = {normalize_alias_search(item["name"]): item for item in breeders if item["name"]}
        ordered = sorted(
            deduplicated.values(),
            key=lambda item: (
                confidence_rank.get(item["confidence"], 0),
                item["rightsRecordCount"],
                item["name"].lower(),
            ),
            reverse=True,
        )
        company_profile["affiliatedBreederCount"] = len(ordered)
        company_profile["affiliatedBreeders"] = ordered[:75]


def build_profiles(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    current_year = TODAY.year
    alias_map = build_name_alias_map(records)
    record_index = {clean_text(row.get("id")): row for row in records if clean_text(row.get("id"))}

    for row in records:
        year = record_year(row)
        exp_date, exp_basis = expiration_date(row)
        exp = parse_date(exp_date)
        owners = owner_candidates(row, alias_map)
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
                    "companyContactUrl": company_profile.get("contactUrl", "") if company_profile else "",
                    "companyLinkedInUrl": company_profile.get("linkedinUrl", "") if company_profile else "",
                    "companyNewsLinks": company_profile.get("newsLinks", []) if company_profile else [],
                    "targetFit": company_profile.get("targetFit", "") if company_profile else "",
                    "acquisitionScaleClass": company_profile.get("acquisitionScaleClass", "") if company_profile else "",
                    "recordCount": 0,
                    "_cultivarLabels": set(),
                    "ownerRoleCounts": Counter(),
                    "confidenceCounts": Counter(),
                    "cropCounts": Counter(),
                    "jurisdictionCounts": Counter(),
                    "sourceKindCounts": Counter(),
                    "registerCounts": Counter(),
                    "statusCounts": Counter(),
                    "years": Counter(),
                    "expirationYears": Counter(),
                    "ownerScopedYears": Counter(),
                    "ownerScopedExpirationYears": Counter(),
                    "namedBreeders": Counter(),
                    "namedInventors": Counter(),
                    "_recordIds": set(),
                    "_recordRoles": defaultdict(set),
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
                    "ownerScopedRecordCount": 0,
                    "ownerScopedRelevantRecordCount": 0,
                    "ownerScopedProtectedIpCount": 0,
                    "ownerScopedActiveProtectionCount": 0,
                    "ownerScopedExpiredProtectionCount": 0,
                    "ownerScopedExpirationNext1Year": 0,
                    "ownerScopedExpirationNext3Years": 0,
                    "ownerScopedExpirationNext5Years": 0,
                    "individualOwner": False if company_profile else looks_individual(owner_display),
                },
            )
            if company_profile and not profile.get("companyWebsite"):
                profile["companyWebsite"] = company_profile.get("website", "")
                profile["companyDescription"] = company_profile.get("description", "")
                profile["companySourceUrl"] = company_profile.get("sourceUrl", "")
                profile["companyContactUrl"] = company_profile.get("contactUrl", "")
                profile["companyLinkedInUrl"] = company_profile.get("linkedinUrl", "")
                profile["companyNewsLinks"] = company_profile.get("newsLinks", [])
                profile["targetFit"] = company_profile.get("targetFit", "")
                profile["acquisitionScaleClass"] = company_profile.get("acquisitionScaleClass", "")

            profile["recordCount"] += 1
            cultivar_label = clean_text(row.get("cultivar") or row.get("title")).lower()
            if cultivar_label:
                profile["_cultivarLabels"].add(cultivar_label)
            record_id = clean_text(row.get("id"))
            profile["_recordIds"].add(record_id)
            profile["_recordRoles"][record_id].add(owner_role)
            profile["ownerRoleCounts"][owner_role] += 1
            profile["confidenceCounts"][confidence] += 1
            if owner_role == "Patent assignee":
                profile["legalOwnerRecordCount"] += 1
                profile["ownerScopedRecordCount"] += 1
            elif owner_role in {"CPVO breeder", "Breeder"}:
                profile["breederSignalRecordCount"] += 1
            elif owner_role == "Inventor":
                profile["inventorSignalRecordCount"] += 1
            relevant_crop = is_relevant_sourcing_crop(row)
            if relevant_crop:
                profile["relevantIpRecordCount"] += 1
                if owner_role == "Patent assignee":
                    profile["relevantLegalOwnerRecordCount"] += 1
                    profile["ownerScopedRelevantRecordCount"] += 1
            profile["cropCounts"][clean_text(row.get("crop")) or "Unclassified"] += 1
            profile["jurisdictionCounts"][jurisdiction(row)] += 1
            profile["sourceKindCounts"][clean_text(row.get("sourceKind")) or clean_text(row.get("source")) or "Unknown"] += 1
            if row.get("registerType"):
                profile["registerCounts"][row["registerType"]] += 1
            if row.get("status"):
                profile["statusCounts"][clean_text(row.get("status"))] += 1
            if year:
                profile["years"][year] += 1
                if owner_role == "Patent assignee":
                    profile["ownerScopedYears"][year] += 1

            breeder_names = {
                canonical_named_party(breeder, alias_map)
                for breeder in split_people_or_entities(row.get("breeders", ""))
            }
            inventor_names = {
                canonical_named_party(inventor, alias_map)
                for inventor in split_people_or_entities(row.get("inventors", ""))
            }
            breeder_names.discard("")
            inventor_names.discard("")
            for breeder in breeder_names:
                profile["namedBreeders"][breeder] += 1
            for inventor in inventor_names:
                profile["namedInventors"][inventor] += 1

            source_kind = clean_text(row.get("sourceKind")).lower()
            is_protected = is_us_plant_patent(row) or ("plant breeders" in source_kind and clean_text(row.get("registerType")).upper() == "PBR")
            if is_protected:
                profile["protectedIpCount"] += 1
                owner_scoped = owner_role == "Patent assignee"
                if owner_scoped:
                    profile["ownerScopedProtectedIpCount"] += 1
                if is_us_plant_patent(row):
                    profile["usPlantPatentCount"] += 1
                if is_cpvo(row) and clean_text(row.get("registerType")).upper() == "PBR":
                    profile["cpvoPbrCount"] += 1
                if exp:
                    if exp < TODAY:
                        profile["expiredProtectionCount"] += 1
                        if owner_scoped:
                            profile["ownerScopedExpiredProtectionCount"] += 1
                    else:
                        profile["activeProtectionCount"] += 1
                        if owner_scoped:
                            profile["ownerScopedActiveProtectionCount"] += 1
                        days = (exp - TODAY).days
                        if days <= 365:
                            profile["expirationNext1Year"] += 1
                            if owner_scoped:
                                profile["ownerScopedExpirationNext1Year"] += 1
                        if days <= 365 * 3:
                            profile["expirationNext3Years"] += 1
                            if owner_scoped:
                                profile["ownerScopedExpirationNext3Years"] += 1
                        if days <= 365 * 5:
                            profile["expirationNext5Years"] += 1
                            if owner_scoped:
                                profile["ownerScopedExpirationNext5Years"] += 1
                    profile["expirationYears"][exp.year] += 1
                    if owner_scoped:
                        profile["ownerScopedExpirationYears"][exp.year] += 1
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
        profile["distinctCultivarCount"] = len(profile.get("_cultivarLabels", set()))
        crop_counts = dict(profile["cropCounts"].most_common())
        top_crop_count = max(crop_counts.values(), default=0)
        profile["firstYear"] = first_year
        profile["lastYear"] = last_year
        profile["recordsLast3Years"] = sum(count for year, count in profile["years"].items() if year >= current_year - 2)
        profile["recordsLast5Years"] = sum(count for year, count in profile["years"].items() if year >= current_year - 4)
        profile["filingVelocity5Year"] = round(profile["recordsLast5Years"] / 5, 2)
        profile["annualCounts"] = [{"year": year, "count": count} for year, count in sorted(profile["years"].items())]
        profile["expirationSchedule"] = [{"year": year, "count": count} for year, count in sorted(profile["expirationYears"].items())]
        profile["ownerScopedAnnualCounts"] = [
            {"year": year, "count": count}
            for year, count in sorted(profile["ownerScopedYears"].items())
        ]
        profile["ownerScopedExpirationSchedule"] = [
            {"year": year, "count": count}
            for year, count in sorted(profile["ownerScopedExpirationYears"].items())
        ]
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
            "ownerScopedYears",
            "ownerScopedExpirationYears",
            "namedBreeders",
            "namedInventors",
            "sampleRecords",
        ]:
            profile.pop(bulky_key, None)
        profiles.append(profile)

    profiles = add_parent_rollups(profiles, record_index, alias_map)
    apply_profile_audits(profiles)
    apply_breeder_affiliations(profiles)
    apply_acquisition_scores(profiles)
    return sorted(
        profiles,
        key=lambda item: (
            item.get("acquisitionFitScore", 0),
            item.get("sourcingScore", 0),
            item.get("protectedIpCount", 0),
            item.get("recordCount", 0),
        ),
        reverse=True,
    )


def write_profiles(profiles: list[dict[str, Any]]) -> None:
    owner_fields = [
        "id",
        "ownerName",
        "normalizedOwnerName",
        "companyWebsite",
        "companyDescription",
        "companySourceUrl",
        "companyContactUrl",
        "companyLinkedInUrl",
        "companyNewsLinks",
        "targetFit",
        "acquisitionScaleClass",
        "recordCount",
        "distinctCultivarCount",
        "protectedIpCount",
        "usPlantPatentCount",
        "cpvoPbrCount",
        "legalOwnerRecordCount",
        "breederSignalRecordCount",
        "inventorSignalRecordCount",
        "relevantIpRecordCount",
        "relevantLegalOwnerRecordCount",
        "ownerScopedRecordCount",
        "ownerScopedRelevantRecordCount",
        "ownerScopedProtectedIpCount",
        "ownerScopedActiveProtectionCount",
        "ownerScopedExpiredProtectionCount",
        "ownerScopedExpirationNext1Year",
        "ownerScopedExpirationNext3Years",
        "ownerScopedExpirationNext5Years",
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
        "acquisitionFitScore",
        "acquisitionFitBand",
        "acquisitionFitReasons",
        "acquisitionFitBlockers",
        "sourcingScore",
        "sourcingFlags",
        "topCrops",
        "topJurisdictions",
        "topBreeders",
        "topInventors",
        "ownerRoleCounts",
        "annualCounts",
        "expirationSchedule",
        "ownerScopedAnnualCounts",
        "ownerScopedExpirationSchedule",
        "isParentRollup",
        "rollupChildren",
        *AFFILIATION_FIELDS,
        "affiliatedBreederCount",
        "affiliatedBreeders",
        "auditStatus",
        "auditConfidence",
        "webResearchStatus",
        "webResearchReviewedAt",
        "webResearchSources",
        "webResearchNotes",
        "ownershipType",
        "ownershipSummary",
        "parentCompany",
        "headquarters",
        "leadershipSummary",
        "websiteCultivarCount",
        "websiteCultivarCountBasis",
        "websiteCultivarEvidenceUrl",
        "primaryContactName",
        "primaryContactTitle",
        "primaryContactEmail",
        "primaryContactPhone",
        "primaryContactUrl",
        "contactSourceUrl",
        "trademarkStatus",
        "trademarkOwner",
        "trademarkEvidenceUrl",
        "trademarkLastCheckedAt",
        "brandExamples",
        "auditNotes",
        "candidateParent",
        "candidateParentBasis",
        "candidateParentConfidence",
        "candidateParentEvidenceUrl",
    ]
    metadata = {
        "title": "Owner Sourcing Profiles",
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "recordCount": len(profiles),
        "methodNotes": [
            "USPTO records use assignee first, then breeder/inventor fallback.",
            "CPVO Variety Finder exports currently expose breeder names, not full holder/applicant fields, so CPVO owner profiles are breeder-signal profiles.",
            "Record count is the number of jurisdiction/register observations; distinct variety labels are normalized display labels and may not equal distinct legal varieties.",
            "US plant patent expiry is estimated as 20 years from filing date where filing date is available.",
            "CPVO PBR expiry is estimated as 25 years, or 30 years for tree/vine crops, from grant date when available or application date otherwise.",
            "Acquisition-fit score is separate from the IP/sourcing score and intentionally penalizes benchmark-scale, public, or institutionally owned platforms.",
            "Breeder affiliations are relationship evidence only. They do not transfer portfolio ownership beyond record-specific assignee or holder evidence.",
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
