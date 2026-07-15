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
    plant_records = records_from(plant_path)
    cpvo_records = records_from(cpvo_path)
    owner_payload = load_json(owner_path)

    payload = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "strategy": "USPTO Official Gazette refreshes automatically through GitHub Actions. CPVO is currently refreshed when new Variety Finder Excel exports are saved and imported. Owner profiles are rebuilt after each data refresh.",
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
        ],
        "futureFeeds": [
            "USPTO assignment alerts for ownership changes",
            "Trademark status checks for variety brands",
            "Additional national PBR databases where bulk exports or stable gazettes are available",
            "Company website portfolio monitors for known breeders and nurseries",
        ],
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
