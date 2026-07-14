#!/usr/bin/env python3
"""Download CPVO Official Gazette PDFs and build a local manifest."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
PDF_DIR = DATA_DIR / "cpvo" / "gazettes"
MANIFEST_PATH = DATA_DIR / "cpvo_gazettes.json"
CPVO_PUBLICATIONS_URL = "https://cpvo.europa.eu/en/applications-and-examinations/official-publications"


ARTICLE_RE = re.compile(
    r'<article\b(?P<article>.*?)</article>',
    re.I | re.S,
)
TITLE_RE = re.compile(r'<span class="field-wrapper">(?P<title>Issue\s*#?\s*[^<]+)</span>', re.I)
DATE_RE = re.compile(r'<time datetime="(?P<iso>[^"]+)">(?P<label>[^<]+)</time>', re.I)
PDF_RE = re.compile(r'href="(?P<href>[^"]+\.pdf)"', re.I)


def fetch_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": "PlantPatentDashboard/1.0"})
    with urlopen(req, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_bytes(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "PlantPatentDashboard/1.0"})
    with urlopen(req, timeout=120) as response:
        return response.read()


def parse_issue_number(title: str) -> int | None:
    match = re.search(r"#\s*(\d+)", title)
    return int(match.group(1)) if match else None


def safe_filename(year: int, issue: int | None, href: str) -> str:
    suffix = Path(href).suffix.lower() or ".pdf"
    issue_part = f"{issue:02d}" if issue is not None else "unknown"
    return f"cpvo_official_gazette_{year}_{issue_part}{suffix}"


def discover_issues(start_year: int, end_year: int) -> list[dict]:
    html = fetch_text(CPVO_PUBLICATIONS_URL)
    issues: list[dict] = []
    for article_match in ARTICLE_RE.finditer(html):
        article = article_match.group("article")
        title_match = TITLE_RE.search(article)
        date_match = DATE_RE.search(article)
        pdf_match = PDF_RE.search(article)
        if not (title_match and date_match and pdf_match):
            continue

        title = re.sub(r"\s+", " ", title_match.group("title")).strip()
        if not title.lower().startswith("issue"):
            continue

        issue_date = date_match.group("iso")[:10]
        year = int(issue_date[:4])
        if year < start_year or year > end_year:
            continue

        href = pdf_match.group("href")
        issue_number = parse_issue_number(title)
        filename = safe_filename(year, issue_number, href)
        issues.append(
            {
                "title": title,
                "year": year,
                "issue": issue_number,
                "publicationDate": issue_date,
                "cpvoPageUrl": urljoin("https://cpvo.europa.eu", re.search(r'href="([^"]+)"><span class="field-wrapper">' + re.escape(title), article).group(1))
                if re.search(r'href="([^"]+)"><span class="field-wrapper">' + re.escape(title), article)
                else CPVO_PUBLICATIONS_URL,
                "sourceUrl": urljoin("https://cpvo.europa.eu", href),
                "localPath": f"data/cpvo/gazettes/{filename}",
                "filename": filename,
            }
        )
    return sorted(issues, key=lambda item: (item["publicationDate"], item["issue"] or 0), reverse=True)


def read_existing_manifest() -> dict[str, dict]:
    if not MANIFEST_PATH.exists():
        return {}
    try:
        payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {item.get("filename", ""): item for item in payload.get("gazettes", [])}


def download_issues(issues: list[dict], force: bool = False) -> list[dict]:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    existing_manifest = read_existing_manifest()
    downloaded: list[dict] = []
    for issue in issues:
        target = PDF_DIR / issue["filename"]
        was_downloaded = False
        if force or not target.exists():
            data = fetch_bytes(issue["sourceUrl"])
            target.write_bytes(data)
            was_downloaded = True
        data = target.read_bytes()
        existing = existing_manifest.get(issue["filename"], {})
        digest = hashlib.sha256(data).hexdigest()
        issue = {
            **issue,
            "bytes": len(data),
            "sha256": digest,
            "downloadedAt": existing.get("downloadedAt")
            if not was_downloaded and existing.get("sha256") == digest
            else dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        downloaded.append(issue)
        print(f"{issue['publicationDate']} {issue['title']}: {target.name} ({issue['bytes']:,} bytes)")
    return downloaded


def write_manifest(issues: list[dict], start_year: int, end_year: int) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    previous_generated_at = None
    previous = None
    if MANIFEST_PATH.exists():
        try:
            previous = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            previous_generated_at = previous.get("metadata", {}).get("generatedAt")
        except (OSError, json.JSONDecodeError):
            previous = None

    generated_at = dt.datetime.now(dt.timezone.utc).isoformat()
    if previous and previous.get("gazettes") == issues:
        generated_at = previous_generated_at or generated_at

    payload = {
        "metadata": {
            "title": "CPVO Official Gazette PDF Manifest",
            "source": CPVO_PUBLICATIONS_URL,
            "generatedAt": generated_at,
            "startYear": start_year,
            "endYear": end_year,
            "recordCount": len(issues),
        },
        "gazettes": issues,
    }
    MANIFEST_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, default=2024)
    parser.add_argument("--end-year", type=int, default=dt.date.today().year)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    issues = discover_issues(args.start_year, args.end_year)
    if not issues:
        print("No CPVO Official Gazette issues found for the requested year range.", file=sys.stderr)
        return 1
    downloaded = download_issues(issues, force=args.force)
    write_manifest(downloaded, args.start_year, args.end_year)
    print(f"Wrote {MANIFEST_PATH} with {len(downloaded)} issues.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
