#!/usr/bin/env python3
"""Build a refresh/status manifest for dashboard data sources."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_PATH = DATA_DIR / "source_status.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def records_from(path: Path) -> list[dict[str, Any]]:
    return load_json(path).get("records", [])


def latest_date(records: list[dict[str, Any]]) -> str:
    dates = sorted((str(row.get("date", "")) for row in records if row.get("date")), reverse=True)
    return dates[0] if dates else ""


def file_timestamp(path: Path) -> str:
    if not path.exists():
        return ""
    return dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat()


def main() -> int:
    plant_path = DATA_DIR / "plant_patents.json"
    cpvo_path = DATA_DIR / "cpvo_varieties.json"
    owner_path = DATA_DIR / "owner_profiles.json"
    research_path = DATA_DIR / "web_research_queue.json"
    affiliation_path = DATA_DIR / "breeder_affiliations.json"
    plant_records = records_from(plant_path)
    cpvo_records = records_from(cpvo_path)
    owner_payload = load_json(owner_path)
    research_payload = load_json(research_path)
    affiliation_payload = load_json(affiliation_path)
    research_metadata = research_payload.get("metadata", {})

    payload = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "strategy": "USPTO Official Gazette refreshes automatically through GitHub Actions. CPVO is currently refreshed when new Variety Finder Excel exports are saved and imported. Owner profiles, internal research queues, and data-contract health checks are rebuilt after each data refresh.",
        "sources": [
            {
                "name": "USPTO Official Gazette plant grants",
                "mode": "automated",
                "cadence": "Daily check for weekly Gazette issues",
                "recordCount": len(plant_records),
                "latestRecordDate": latest_date(plant_records),
                "lastFileUpdate": file_timestamp(plant_path),
                "nextStep": "Keep the scheduled GitHub Action active; it will pick up newly published Gazette issues.",
            },
            {
                "name": "CPVO Variety Finder exports",
                "mode": "manual import",
                "cadence": "Refresh when new CPVO Excel pulls are downloaded",
                "recordCount": len(cpvo_records),
                "latestRecordDate": latest_date(cpvo_records),
                "lastFileUpdate": file_timestamp(cpvo_path),
                "nextStep": "Download new CPVO workbook exports for priority crops, then run scripts/import_cpvo_varieties.py.",
            },
            {
                "name": "Owner / breeder sourcing profiles",
                "mode": "derived",
                "cadence": "Rebuilt after USPTO or CPVO data changes",
                "recordCount": owner_payload.get("metadata", {}).get("recordCount", 0),
                "latestRecordDate": "",
                "lastFileUpdate": file_timestamp(owner_path),
                "nextStep": "Review aliases in config/company_profiles.json as new breeders appear.",
            },
            {
                "name": "Company and breeder web research ledger",
                "mode": "continuous public-source review",
                "cadence": "Resumable evidence batches; known domains rechecked during QA passes",
                "recordCount": research_metadata.get("profileCount", 0),
                "completedCount": research_metadata.get("reviewLevelCounts", {}).get("complete", 0),
                "partialCount": research_metadata.get("reviewLevelCounts", {}).get("partial", 0),
                "latestRecordDate": "",
                "lastFileUpdate": file_timestamp(research_path),
                "nextStep": "Work the highest-priority unresolved companies and breeder affiliations, recording only source-backed findings.",
            },
            {
                "name": "Breeder affiliation graph",
                "mode": "derived relationship evidence",
                "cadence": "Rebuilt after USPTO or CPVO data changes",
                "recordCount": affiliation_payload.get("metadata", {}).get("recordCount", 0),
                "verifiedCount": affiliation_payload.get("metadata", {}).get("verifiedRelationshipCount", 0),
                "probableCount": affiliation_payload.get("metadata", {}).get("probableRelationshipCount", 0),
                "latestRecordDate": "",
                "lastFileUpdate": file_timestamp(affiliation_path),
                "nextStep": "Verify review-queue relationships with official company, university, and registry sources; never infer blanket ownership from employment.",
            },
        ],
        "futureFeeds": [
            "USPTO assignment alerts for ownership changes",
            "Automated trademark status-change monitoring for source-linked variety brands",
            "Additional national PBR databases where bulk exports or stable gazettes are available",
            "Broader holder/applicant fields from future CPVO or UPOV exports",
        ],
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
