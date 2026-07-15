from __future__ import annotations

import csv
import datetime as dt
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
COMPANY_PROFILE_PATH = ROOT / "config" / "company_profiles.json"
OUTPUT_JSON = ROOT / "data" / "company_site_probe.json"
OUTPUT_CSV = ROOT / "data" / "company_site_probe.csv"

KEYWORDS = [
    "variety",
    "varieties",
    "cultivar",
    "cultivars",
    "genetic",
    "genetics",
    "patent",
    "trademark",
    "brand",
    "blueberry",
    "strawberry",
    "raspberry",
    "blackberry",
    "grape",
    "apple",
    "peach",
    "nectarine",
    "plum",
    "cherry",
]


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_fetch(url: str) -> dict[str, Any]:
    context = ssl._create_unverified_context()
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20, context=context) as response:
            body = response.read(750_000).decode("utf-8", "ignore")
            return {
                "ok": True,
                "status": response.status,
                "finalUrl": response.geturl(),
                "html": body,
                "error": "",
            }
    except urllib.error.HTTPError as error:
        return {
            "ok": False,
            "status": error.code,
            "finalUrl": getattr(error, "url", url),
            "html": "",
            "error": f"HTTP {error.code}",
        }
    except Exception as error:  # noqa: BLE001 - this is an audit/probe utility.
        return {
            "ok": False,
            "status": "",
            "finalUrl": url,
            "html": "",
            "error": f"{type(error).__name__}: {str(error)[:160]}",
        }


def html_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
    if not match:
        return ""
    return clean_text(re.sub(r"<[^>]+>", " ", match.group(1)))


def link_candidates(base_url: str, html: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for match in re.finditer(r"<a\b([^>]*)>(.*?)</a>", html, flags=re.I | re.S):
        attrs, label_html = match.groups()
        href_match = re.search(r"href\s*=\s*(['\"])(.*?)\1", attrs, flags=re.I | re.S)
        if not href_match:
            continue
        href = href_match.group(2).strip()
        if not href or href.startswith("#") or href.lower().startswith(("mailto:", "tel:", "javascript:")):
            continue
        label = clean_text(re.sub(r"<[^>]+>", " ", label_html))
        haystack = f"{href} {label}".lower()
        if any(keyword in haystack for keyword in KEYWORDS):
            links.append(
                {
                    "label": label[:120],
                    "url": urllib.parse.urljoin(base_url, href),
                }
            )
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for link in links:
        if link["url"] in seen:
            continue
        seen.add(link["url"])
        deduped.append(link)
    return deduped[:12]


def probe_company(profile: dict[str, Any]) -> dict[str, Any]:
    website = clean_text(profile.get("website"))
    response = safe_fetch(website) if website else {"ok": False, "status": "", "finalUrl": "", "html": "", "error": "No website"}
    html = response.pop("html", "")
    lowered = html.lower()
    keyword_counts = {keyword: lowered.count(keyword) for keyword in KEYWORDS if lowered.count(keyword)}
    return {
        "canonicalName": clean_text(profile.get("canonicalName")),
        "website": website,
        "ok": response["ok"],
        "status": response["status"],
        "finalUrl": response["finalUrl"],
        "error": response["error"],
        "title": html_title(html),
        "keywordCounts": keyword_counts,
        "evidenceLinks": link_candidates(response.get("finalUrl") or website, html),
        "probedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def flatten_for_csv(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonicalName": row["canonicalName"],
        "website": row["website"],
        "ok": row["ok"],
        "status": row["status"],
        "finalUrl": row["finalUrl"],
        "error": row["error"],
        "title": row["title"],
        "keywordCounts": " | ".join(f"{key}:{value}" for key, value in row["keywordCounts"].items()),
        "evidenceLinks": " | ".join(
            f"{link.get('label') or 'link'} <{link.get('url')}>" for link in row["evidenceLinks"]
        ),
        "probedAt": row["probedAt"],
    }


def main() -> int:
    profiles = read_json(COMPANY_PROFILE_PATH)
    rows = [probe_company(profile) for profile in profiles if clean_text(profile.get("canonicalName"))]
    payload = {
        "metadata": {
            "title": "Company Website Probe",
            "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
            "profileCount": len(rows),
            "methodNotes": [
                "This validates public website availability and finds likely cultivar/variety evidence links.",
                "Keyword counts are page-level hints, not cultivar counts.",
                "LinkedIn is intentionally excluded because it often blocks automated checks.",
            ],
        },
        "companies": rows,
    }
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    csv_rows = [flatten_for_csv(row) for row in rows]
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(csv_rows[0]) if csv_rows else [])
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"Wrote {OUTPUT_JSON} and {OUTPUT_CSV} with {len(rows):,} company probes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
