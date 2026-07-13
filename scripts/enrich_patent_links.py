from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "plant_patents.json"
CACHE_PATH = ROOT / "data" / "link_enrichment_cache.json"
USER_AGENT = "PlantPatentDashboard/0.1 (+patent link enrichment)"
MAX_WORKERS = 8


def load_json(path: Path, default: Any) -> Any:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def record_text(row: dict[str, Any]) -> str:
    return " ".join(
        str(row.get(key) or "")
        for key in ("primarySource", "patentNumber", "publicationNumber", "id", "title", "notes")
    )


def extract_uspp(text: str) -> str:
    patterns = [
        r"\bUSPP\s*0*([0-9][0-9,\.\s]{3,10}[0-9])\b",
        r"\bUS\s*PP\s*0*([0-9][0-9,\.\s]{3,10}[0-9])\b",
        r"\bPP0*([0-9]{5,6})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text or "", re.I)
        if match:
            number = re.sub(r"\D", "", match.group(1))
            if number.isdigit():
                return str(int(number))
    return ""


def extract_usppa(text: str) -> str:
    match = re.search(r"\bUSPPA\s*([0-9]{11})\b", text or "", re.I)
    return match.group(1) if match else ""


def candidate_for(row: dict[str, Any]) -> tuple[str, str, str]:
    text = record_text(row)
    uspp = extract_uspp(text)
    if uspp:
        return ("USPPPDF", uspp, f"https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/PP{uspp}")
    usppa = extract_usppa(text)
    if usppa:
        return ("USPPAPDF", usppa, f"https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/{usppa}")
    return ("", "", "")


def url_exists(url: str) -> tuple[bool, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=25) as response:
            status = response.status
            content_type = response.headers.get("Content-Type", "")
            body = response.read(4096).decode("utf-8", errors="ignore")
        if status == 200 and "Error 404" not in body and "not found" not in body.lower():
            return True, content_type
        return False, f"status={status}"
    except HTTPError as exc:
        return False, f"status={exc.code}"
    except (URLError, TimeoutError) as exc:
        return False, str(exc)


def main() -> None:
    payload = load_json(DATA_PATH, {"metadata": {}, "records": []})
    records = payload.get("records", [])
    cache = load_json(CACHE_PATH, {})
    work: dict[str, str] = {}

    for row in records:
        kind, number, url = candidate_for(row)
        if kind == "USPPPDF" and row.get("sourceUrl") and "patentsgazette.uspto.gov" in str(row.get("sourceUrl")):
            row["gazetteUrl"] = row["sourceUrl"]
            row.pop("sourceUrl", None)
            row.pop("verifiedSource", None)
        if row.get("sourceUrl") and row.get("verifiedSource") != "Google Patents":
            continue
        if not url:
            continue
        cache_key = f"{kind}:{number}"
        if cache.get(cache_key, {}).get("verified"):
            continue
        if cache.get(cache_key, {}).get("verified") is False:
            continue
        work[cache_key] = url

    print(f"Records: {len(records)}")
    print(f"Patent candidates needing verification: {len(work)}")

    completed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {executor.submit(url_exists, url): (key, url) for key, url in work.items()}
        for future in as_completed(future_map):
            key, url = future_map[future]
            verified, note = future.result()
            cache[key] = {
                "url": url,
                "verified": verified,
                "note": note,
                "checkedAt": datetime.now(timezone.utc).isoformat(),
            }
            completed += 1
            if completed % 100 == 0:
                print(f"Checked {completed}/{len(work)}")
                save_json(CACHE_PATH, cache)
            time.sleep(0.02)

    linked = 0
    for row in records:
        kind, number, _url = candidate_for(row)
        if kind == "USPPPDF" and row.get("sourceUrl") and "patentsgazette.uspto.gov" in str(row.get("sourceUrl")):
            row["gazetteUrl"] = row["sourceUrl"]
            row.pop("sourceUrl", None)
            row.pop("verifiedSource", None)
        if row.get("sourceUrl") and row.get("verifiedSource") != "Google Patents":
            continue
        if not kind:
            continue
        result = cache.get(f"{kind}:{number}")
        if result and result.get("verified"):
            row["sourceUrl"] = result["url"]
            row["verifiedSource"] = "USPTO Patent Public Search PDF"
            row["verifiedAt"] = datetime.now(timezone.utc).isoformat()
            linked += 1

    payload.setdefault("metadata", {})["lastLinkEnrichment"] = datetime.now(timezone.utc).isoformat()
    payload["metadata"]["lastLinkEnrichmentLinked"] = linked
    payload["metadata"]["lastLinkEnrichmentCandidates"] = len(work)
    save_json(DATA_PATH, payload)
    save_json(CACHE_PATH, cache)

    verified_total = sum(1 for row in records if row.get("sourceUrl"))
    print(f"Linked {linked} additional records.")
    print(f"Total records with sourceUrl: {verified_total}")


if __name__ == "__main__":
    main()
