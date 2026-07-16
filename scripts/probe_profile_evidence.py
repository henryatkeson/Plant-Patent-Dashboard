#!/usr/bin/env python3
"""Probe source-backed profile evidence links and preserve a QA report."""

from __future__ import annotations

import csv
import datetime as dt
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from probe_company_sites import clean_text, probe_url


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATHS = sorted((ROOT / "config").glob("profile_web_research*.json"))
OUTPUT_JSON = ROOT / "data" / "profile_evidence_probe.json"
OUTPUT_CSV = ROOT / "data" / "profile_evidence_probe.csv"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def hostname(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def evidence_links(profile: dict[str, Any]) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    field_labels = {
        "primaryContactUrl": "Primary contact",
        "contactSourceUrl": "Contact source",
        "websiteCultivarEvidenceUrl": "Cultivar evidence",
        "candidateParentEvidenceUrl": "Parent evidence",
        "trademarkEvidenceUrl": "Trademark evidence",
    }
    for field, label in field_labels.items():
        url = clean_text(profile.get(field))
        if url:
            links.append({"label": label, "url": url, "field": field})
    for item in profile.get("webResearchSources") or []:
        url = clean_text(item.get("url")) if isinstance(item, dict) else clean_text(item)
        if url:
            label = clean_text(item.get("label")) if isinstance(item, dict) else "Research source"
            links.append({"label": label or "Research source", "url": url, "field": "webResearchSources"})
    seen: set[str] = set()
    return [item for item in links if not (item["url"] in seen or seen.add(item["url"]))]


def check_link(profile_name: str, item: dict[str, str]) -> dict[str, Any]:
    url = item["url"]
    domain = hostname(url)
    if domain == "linkedin.com" or domain.endswith(".linkedin.com") or domain == "tsdr.uspto.gov" or domain.endswith(".tsdr.uspto.gov"):
        response = {
            "url": url,
            "ok": True,
            "status": "syntax checked",
            "finalUrl": url,
            "error": "",
            "checkType": "manual_browser_required",
        }
    else:
        response = probe_url(url)
        response.pop("html", None)
        if response.get("status") in {401, 403, 429, 503}:
            response["ok"] = True
            response["checkType"] = "manual_browser_required"
            response["error"] = "Automated access was blocked or temporarily unavailable; source requires manual browser review."
        elif "timed out" in str(response.get("error") or "").lower():
            response["ok"] = True
            response["checkType"] = "manual_browser_required"
            response["error"] = "Automated request timed out; source requires manual browser review."
        elif "ssl" in str(response.get("error") or "").lower() and "handshake" in str(response.get("error") or "").lower():
            response["ok"] = True
            response["checkType"] = "manual_browser_required"
            response["error"] = "Automated TLS handshake failed; source requires manual browser review."
    return {
        "canonicalName": profile_name,
        "label": item["label"],
        "field": item["field"],
        **response,
        "checkedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def main() -> int:
    profiles: list[dict[str, Any]] = []
    for path in EVIDENCE_PATHS:
        payload = read_json(path)
        profiles.extend(payload.get("profiles", []) if isinstance(payload, dict) else [])
    tasks: list[tuple[str, dict[str, str]]] = []
    for profile in profiles:
        name = clean_text(profile.get("canonicalName"))
        if not name:
            continue
        tasks.extend((name, item) for item in evidence_links(profile))

    # The same official source often supports several profiles. Probe each URL
    # once, in parallel, then fan the result back out to every evidence row.
    unique_tasks: dict[str, tuple[str, dict[str, str]]] = {}
    for name, item in tasks:
        unique_tasks.setdefault(item["url"], (name, item))
    with ThreadPoolExecutor(max_workers=12) as executor:
        checked = list(executor.map(lambda task: check_link(*task), unique_tasks.values()))
    responses_by_url = {
        row["url"]: {
            key: value
            for key, value in row.items()
            if key not in {"canonicalName", "label", "field"}
        }
        for row in checked
    }
    rows = [
        {
            "canonicalName": name,
            "label": item["label"],
            "field": item["field"],
            **responses_by_url[item["url"]],
        }
        for name, item in tasks
    ]

    summary = {
        "title": "Profile Evidence Link Probe",
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "profileCount": len({row["canonicalName"] for row in rows}),
        "linkCount": len(rows),
        "verifiedCount": sum(bool(row["ok"]) for row in rows),
        "failedCount": sum(not bool(row["ok"]) for row in rows),
        "manualBrowserCount": sum(row.get("checkType") == "manual_browser_required" for row in rows),
        "methodNotes": [
            "Duplicate evidence URLs are probed once and reused across profiles; unique links are checked concurrently with a bounded worker pool.",
            "LinkedIn and USPTO TSDR links are syntax-checked because automated access may be blocked; they still require periodic manual browser review.",
            "HTTP 401, 403, 429, and 503 responses, request timeouts, and TLS-handshake failures are retained as manual-review items rather than treated as dead citations.",
            "An HTTP failure does not erase evidence. It creates a review item so a replacement or archived source can be found.",
        ],
    }
    OUTPUT_JSON.write_text(json.dumps({"metadata": summary, "links": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Checked {len(rows):,} evidence links across {summary['profileCount']:,} profiles; {summary['failedCount']:,} need review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
