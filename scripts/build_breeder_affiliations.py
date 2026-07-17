#!/usr/bin/env python3
"""Build evidence-scoped breeder-to-company affiliation relationships."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

import build_owner_profiles as profiles


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CONFIG_PATH = ROOT / "config" / "breeder_affiliations.json"
OUTPUT_PATH = DATA_DIR / "breeder_affiliations.json"
CSV_PATH = DATA_DIR / "breeder_affiliations.csv"

CONFIDENCE_VALUES = {"high", "medium", "low", "unverified"}
RIGHTS_BASIS_VALUES = {"none", "assignee_on_scoped_patent_records", "registered_holder"}
EVIDENCE_WEIGHTS = {"patent_assignee": 8, "co_listed_entity": 5, "cultivar_match": 1}


def clean_confidence(value: Any) -> str:
    text = profiles.clean_text(value).lower()
    if text.startswith("high"):
        return "high"
    if text.startswith("medium"):
        return "medium"
    if text.startswith("low"):
        return "low"
    return "unverified"


def infer_identity_confidence(name: str) -> str:
    if not profiles.looks_individual(name):
        return "unverified"
    tokens = profiles.person_tokens(name)
    if not 2 <= len(tokens) <= 4:
        return "low"
    if any(len(token) == 1 for token in tokens):
        return "medium"
    return "high"


def affiliation_status(relationship_confidence: str, identity_confidence: str) -> str:
    if identity_confidence == "unverified":
        return "unresolved"
    if identity_confidence == "low":
        return "review_required"
    if identity_confidence == "medium" and relationship_confidence == "high":
        return "probable_relationship"
    return {
        "high": "verified_relationship",
        "medium": "probable_relationship",
        "low": "review_required",
        "unverified": "unresolved",
    }[relationship_confidence]


def load_manual_affiliations(record_ids: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if CONFIG_PATH.exists():
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        rows.extend(payload.get("affiliations", []))

    for audit in profiles.PROFILE_AUDITS.values():
        breeder = profiles.clean_text(audit.get("canonicalName") or audit.get("ownerName"))
        company = profiles.clean_text(audit.get("candidateParent"))
        candidate_confidence = clean_confidence(audit.get("candidateParentConfidence"))
        if (
            not breeder
            or not company
            or not profiles.looks_individual(breeder)
            or candidate_confidence == "unverified"
        ):
            continue
        sources = []
        evidence_url = profiles.clean_text(audit.get("candidateParentEvidenceUrl"))
        if evidence_url:
            sources.append({"label": "Affiliation evidence", "url": evidence_url})
        for source in audit.get("webResearchSources") or []:
            if not isinstance(source, dict):
                continue
            url = profiles.clean_text(source.get("url"))
            if url and all(item.get("url") != url for item in sources):
                sources.append({"label": profiles.clean_text(source.get("label")) or "Public source", "url": url})
        rows.append(
            {
                "breederName": breeder,
                "companyName": company,
                "relationshipType": "public-source affiliation",
                "identityConfidence": "high",
                "relationshipConfidence": candidate_confidence,
                "rightsBasis": "none",
                "recordIds": [],
                "evidence": sources[:5],
                "reviewedAt": profiles.clean_text(audit.get("webResearchReviewedAt")),
                "basis": profiles.clean_text(audit.get("candidateParentBasis")),
                "source": "profile research ledger",
            }
        )

    validated: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        breeder = profiles.canonical_named_party(profiles.clean_text(row.get("breederName")), {})
        company = profiles.canonical_owner_name(profiles.clean_text(row.get("companyName")))
        if not breeder or not company:
            continue
        identity_confidence = clean_confidence(row.get("identityConfidence"))
        relationship_confidence = clean_confidence(row.get("relationshipConfidence"))
        rights_basis = profiles.clean_text(row.get("rightsBasis")) or "none"
        if identity_confidence not in CONFIDENCE_VALUES or relationship_confidence not in CONFIDENCE_VALUES:
            raise ValueError(f"Invalid confidence value for {breeder} -> {company}")
        if rights_basis not in RIGHTS_BASIS_VALUES:
            raise ValueError(f"Invalid rights basis for {breeder} -> {company}: {rights_basis}")
        scoped_records = [profiles.clean_text(value) for value in row.get("recordIds", []) if profiles.clean_text(value)]
        missing_records = sorted(set(scoped_records) - record_ids)
        if missing_records:
            raise ValueError(f"Unknown affiliation record IDs for {breeder}: {missing_records[:5]}")
        key = (profiles.normalize_owner_name(breeder), profiles.normalize_owner_name(company))
        if key in seen:
            continue
        seen.add(key)
        validated.append(
            {
                **row,
                "breederName": breeder,
                "companyName": company,
                "identityConfidence": identity_confidence,
                "relationshipConfidence": relationship_confidence,
                "rightsBasis": rights_basis,
                "recordIds": scoped_records,
            }
        )
    return validated


def infer_confidence(counts: Counter[str], direct_share: float, second_score: int) -> str:
    patent_count = counts["patent_assignee"]
    co_listed_count = counts["co_listed_entity"]
    cultivar_count = counts["cultivar_match"]
    score = sum(EVIDENCE_WEIGHTS[key] * counts[key] for key in EVIDENCE_WEIGHTS)
    if patent_count >= 2 and direct_share >= 0.6 and score >= max(16, round(second_score * 1.5)):
        return "high"
    if co_listed_count >= 3 and direct_share >= 0.75 and score >= max(15, round(second_score * 1.5)):
        return "high"
    if patent_count >= 1 and direct_share >= 0.5 and score >= max(8, second_score * 2):
        return "medium"
    if co_listed_count >= 2 and direct_share >= 0.6 and score >= max(10, second_score * 2):
        return "medium"
    if co_listed_count >= 1 and cultivar_count >= 3 and direct_share >= 0.75 and score >= max(8, second_score * 2):
        return "medium"
    return "low"


def build_affiliations(records: list[dict[str, Any]]) -> dict[str, Any]:
    alias_map = profiles.build_name_alias_map(records)
    record_ids = {profiles.clean_text(row.get("id")) for row in records if profiles.clean_text(row.get("id"))}
    manual_rows = load_manual_affiliations(record_ids)

    names: dict[str, str] = {}
    people: set[str] = set()
    evidence_counts: dict[str, Counter[tuple[str, str]]] = defaultdict(Counter)
    evidence_records: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    cultivar_people: dict[tuple[str, str], set[str]] = defaultdict(set)
    cultivar_entities: dict[tuple[str, str], set[str]] = defaultdict(set)

    @lru_cache(maxsize=None)
    def canonical_party(raw: str) -> tuple[str, str, str] | None:
        name = profiles.canonical_named_party(raw, alias_map)
        normalized = profiles.normalize_owner_name(name)
        if not normalized:
            return None
        if profiles.looks_individual(name):
            kind = "person"
        elif profiles.likely_entity_name(name):
            kind = "entity"
        else:
            kind = "unknown"
        return normalized, name, kind

    @lru_cache(maxsize=None)
    def parsed_parties(value: str) -> tuple[tuple[str, str, str], ...]:
        parties = []
        for raw in profiles.split_people_or_entities(value):
            party = canonical_party(raw)
            if party:
                parties.append(party)
        return tuple(dict.fromkeys(parties))

    def add_evidence(person: str, company: str, kind: str, record_id: str) -> None:
        evidence_counts[person][(company, kind)] += 1
        key = (person, company, kind)
        if record_id and record_id not in evidence_records[key] and len(evidence_records[key]) < 25:
            evidence_records[key].append(record_id)

    for row in records:
        record_id = profiles.clean_text(row.get("id"))
        breeder_parties = parsed_parties(profiles.clean_text(row.get("breeders")))
        person_parties = [party for party in breeder_parties if party[2] == "person"]
        entity_parties = [party for party in breeder_parties if party[2] == "entity"]
        for normalized, name, kind in breeder_parties:
            names[normalized] = name
            if kind == "person":
                people.add(normalized)

        if profiles.is_cpvo(row):
            for person, _name, _kind in person_parties:
                for company, _company_name, _entity_kind in entity_parties:
                    add_evidence(person, company, "co_listed_entity", record_id)

        crop = profiles.clean_text(row.get("crop")).lower()
        cultivar = profiles.normalize_owner_name(row.get("cultivar") or row.get("title") or "")
        if cultivar and cultivar not in {"unknown", "unnamed", "n a", "na"}:
            cultivar_key = (crop, cultivar)
            cultivar_people[cultivar_key].update(party[0] for party in person_parties)
            cultivar_entities[cultivar_key].update(party[0] for party in entity_parties)

        if not profiles.is_cpvo(row):
            inventor_parties = [
                party
                for party in parsed_parties(profiles.clean_text(row.get("inventors")))
                if party[2] == "person"
            ]
            assignee_parties = [
                party
                for party in parsed_parties(profiles.clean_text(row.get("assignee")))
                if party[2] == "entity"
            ]
            for person, person_name, _kind in inventor_parties:
                people.add(person)
                names[person] = person_name
                for company, company_name, _entity_kind in assignee_parties:
                    names[company] = company_name
                    add_evidence(person, company, "patent_assignee", record_id)

    for cultivar_key, cultivar_persons in cultivar_people.items():
        companies = cultivar_entities.get(cultivar_key, set())
        if len(companies) != 1:
            continue
        company = next(iter(companies))
        for person in cultivar_persons:
            add_evidence(person, company, "cultivar_match", "")

    manual_by_person: dict[str, dict[str, Any]] = {}
    for row in manual_rows:
        person = profiles.normalize_owner_name(row["breederName"])
        company = profiles.normalize_owner_name(row["companyName"])
        names[person] = row["breederName"]
        names[company] = row["companyName"]
        people.add(person)
        existing = manual_by_person.get(person)
        if not existing or row["relationshipConfidence"] == "high":
            manual_by_person[person] = row

    rows: list[dict[str, Any]] = []
    for person in sorted(people, key=lambda value: names.get(value, value).lower()):
        company_counts: dict[str, Counter[str]] = defaultdict(Counter)
        for (company, kind), count in evidence_counts.get(person, {}).items():
            company_counts[company][kind] += count
        candidates = []
        direct_total = sum(
            counts["patent_assignee"] + counts["co_listed_entity"]
            for counts in company_counts.values()
        )
        for company, counts in company_counts.items():
            score = sum(EVIDENCE_WEIGHTS[kind] * counts[kind] for kind in EVIDENCE_WEIGHTS)
            direct_count = counts["patent_assignee"] + counts["co_listed_entity"]
            candidates.append(
                {
                    "companyName": names.get(company, company),
                    "normalizedCompanyName": company,
                    "score": score,
                    "directCount": direct_count,
                    "patentAssigneeCount": counts["patent_assignee"],
                    "coListedEntityCount": counts["co_listed_entity"],
                    "cultivarMatchCount": counts["cultivar_match"],
                    "directShare": round(direct_count / max(1, direct_total), 3),
                }
            )
        candidates.sort(key=lambda item: (item["score"], item["directCount"]), reverse=True)

        manual = manual_by_person.get(person)
        if manual:
            company_name = manual["companyName"]
            company = profiles.normalize_owner_name(company_name)
            counts = company_counts.get(company, Counter())
            confidence = manual["relationshipConfidence"]
            basis = manual.get("basis") or "Public-source affiliation recorded in the research ledger."
            source = manual.get("source") or "manual affiliation ledger"
            evidence = manual.get("evidence") or []
            relationship_type = manual.get("relationshipType") or "public-source affiliation"
            identity_confidence = manual.get("identityConfidence") or "high"
            rights_basis = manual.get("rightsBasis") or "none"
            scoped_record_ids = manual.get("recordIds") or []
        elif candidates:
            top = candidates[0]
            company_name = top["companyName"]
            company = top["normalizedCompanyName"]
            counts = company_counts[company]
            second_score = candidates[1]["score"] if len(candidates) > 1 else 0
            confidence = infer_confidence(counts, top["directShare"], second_score)
            evidence_types = []
            if counts["patent_assignee"]:
                evidence_types.append(f"{counts['patent_assignee']} inventor-assignee records")
            if counts["co_listed_entity"]:
                evidence_types.append(f"{counts['co_listed_entity']} co-listed breeder/entity records")
            if counts["cultivar_match"]:
                evidence_types.append(f"{counts['cultivar_match']} same-cultivar records")
            basis = "; ".join(evidence_types)
            source = "record-derived affiliation graph"
            evidence = []
            relationship_type = "breeding-program association"
            identity_confidence = infer_identity_confidence(names.get(person, person))
            rights_basis = "assignee_on_scoped_patent_records" if counts["patent_assignee"] else "none"
            scoped_record_ids = evidence_records.get((person, company, "patent_assignee"), [])
        else:
            company_name = ""
            company = ""
            counts = Counter()
            confidence = "unverified"
            basis = "No company or program evidence found in the current public records."
            source = "record-derived affiliation graph"
            evidence = []
            relationship_type = "unresolved"
            identity_confidence = infer_identity_confidence(names.get(person, person))
            rights_basis = "none"
            scoped_record_ids = []

        direct_count = counts["patent_assignee"] + counts["co_listed_entity"]
        direct_share = round(direct_count / max(1, direct_total), 3) if company else 0
        status = affiliation_status(confidence, identity_confidence)
        evidence_record_ids = []
        if company:
            for kind in EVIDENCE_WEIGHTS:
                evidence_record_ids.extend(evidence_records.get((person, company, kind), []))
        evidence_record_ids = list(dict.fromkeys(evidence_record_ids))[:25]
        rows.append(
            {
                "breederId": profiles.owner_id(person),
                "breederName": names.get(person, person),
                "normalizedBreederName": person,
                "companyName": company_name,
                "normalizedCompanyName": company,
                "relationshipType": relationship_type,
                "identityConfidence": identity_confidence,
                "relationshipConfidence": confidence,
                "status": status,
                "basis": basis,
                "source": source,
                "patentAssigneeCount": counts["patent_assignee"],
                "coListedEntityCount": counts["co_listed_entity"],
                "cultivarMatchCount": counts["cultivar_match"],
                "directEvidenceCount": direct_count,
                "directEvidenceShare": direct_share,
                "rightsBasis": rights_basis,
                "rightsRecordIds": list(dict.fromkeys(scoped_record_ids)),
                "evidenceRecordIds": evidence_record_ids,
                "evidence": evidence[:5],
                "alternatives": candidates[:3],
            }
        )

    counts = Counter(row["status"] for row in rows)
    return {
        "metadata": {
            "title": "Breeder-to-company affiliation graph",
            "methodology": (
                "Relationships are inferred from inventor-assignee records, explicit company/person co-listing, "
                "and same-cultivar corroboration. Affiliation never transfers legal ownership beyond explicitly "
                "scoped assignee or holder records."
            ),
            "recordCount": len(rows),
            "verifiedRelationshipCount": counts["verified_relationship"],
            "probableRelationshipCount": counts["probable_relationship"],
            "reviewRequiredCount": counts["review_required"],
            "unresolvedCount": counts["unresolved"],
        },
        "affiliations": rows,
    }


def write_outputs(payload: dict[str, Any]) -> None:
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    fields = [
        "breederName",
        "companyName",
        "relationshipType",
        "identityConfidence",
        "relationshipConfidence",
        "status",
        "patentAssigneeCount",
        "coListedEntityCount",
        "cultivarMatchCount",
        "directEvidenceCount",
        "directEvidenceShare",
        "rightsBasis",
        "basis",
        "source",
    ]
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(payload["affiliations"])


def main() -> None:
    records = profiles.load_records(profiles.PATENT_PATH) + profiles.load_records(profiles.CPVO_PATH)
    payload = build_affiliations(records)
    write_outputs(payload)
    metadata = payload["metadata"]
    print(
        f"Wrote {metadata['recordCount']:,} breeder relationships: "
        f"{metadata['verifiedRelationshipCount']:,} verified, "
        f"{metadata['probableRelationshipCount']:,} probable, "
        f"{metadata['reviewRequiredCount']:,} review, "
        f"{metadata['unresolvedCount']:,} unresolved."
    )


if __name__ == "__main__":
    main()
