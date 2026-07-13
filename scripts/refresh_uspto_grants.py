from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "plant_patents.json"
KEYWORDS_PATH = ROOT / "config" / "crop_keywords.txt"
OG_INDEX_URL = "https://www.uspto.gov/learning-and-resources/official-gazette/official-gazette-patents"
USER_AGENT = "PlantPatentDashboard/0.1 (+public USPTO data refresh)"


def fetch_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=45) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def clean_html(source: str) -> str:
    source = re.sub(r"<script\b.*?</script>", " ", source, flags=re.I | re.S)
    source = re.sub(r"<style\b.*?</style>", " ", source, flags=re.I | re.S)
    source = re.sub(r"<[^>]+>", " ", source)
    return re.sub(r"\s+", " ", html.unescape(source)).strip()


def load_keywords() -> list[str]:
    terms: list[str] = []
    for line in KEYWORDS_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            terms.append(stripped.lower())
    return sorted(set(terms), key=len, reverse=True)


def find_issues(limit: int) -> list[dict[str, str]]:
    index = fetch_text(OG_INDEX_URL)
    pattern = re.compile(
        r'href="(?P<url>https://patentsgazette\.uspto\.gov/week\d+)"[^>]*>\s*(?P<date>[A-Za-z]+\s+\d{2},\s+\d{4})',
        re.I,
    )
    issues = []
    for match in pattern.finditer(index):
        url = match.group("url").rstrip("/")
        date = datetime.strptime(match.group("date"), "%B %d, %Y").date().isoformat()
        issues.append({"url": url, "date": date})
    return issues[:limit]


def parse_issue(issue: dict[str, str]) -> list[dict[str, str]]:
    patent_page_url = f"{issue['url']}/OG/patent.html"
    page = fetch_text(patent_page_url)
    list_match = re.search(r'patentListString\s*=\s*"([^"]+)"', page)
    folder_match = re.search(r'strHtmlFolder\s*=\s*"([^"]+)"', page)
    issue_date_match = re.search(r'IssueDate\s*=\s*"(\d{8})"', page)
    if not (list_match and folder_match and issue_date_match):
        return []

    folder = folder_match.group(1)
    issue_date = issue_date_match.group(1)
    numbers = [part for part in list_match.group(1).split(",") if part.startswith("PP")]
    return [
        {
            "number": number,
            "issueDate": issue["date"],
            "detailUrl": f"{issue['url']}/OG/{folder}/US{number}-{issue_date}.html",
        }
        for number in numbers
    ]


def extract_between(text: str, start: str, end_pattern: str) -> str:
    match = re.search(re.escape(start) + r"\s*(.*?)\s*(?:" + end_pattern + r")", text, flags=re.I)
    return match.group(1).strip(" .,;") if match else ""


def classify_crop(search_text: str, keywords: list[str]) -> str:
    low = search_text.lower()
    for keyword in keywords:
        if re.search(rf"(?<![a-z]){re.escape(keyword)}(?![a-z])", low):
            return keyword
    return ""


def parse_patent_detail(item: dict[str, str], keywords: list[str]) -> dict[str, Any] | None:
    try:
        html_source = fetch_text(item["detailUrl"])
    except (HTTPError, URLError, TimeoutError) as exc:
        print(f"Warning: could not fetch {item['detailUrl']}: {exc}", file=sys.stderr)
        return None

    text = clean_html(html_source)
    title_match = re.search(r"US\s+(PP[\d,]+)\s+\S+\s+(.*?)(?:\s+Latin Name:|\s+Varietal Denomination:|\s+[A-Z][A-Za-z .'-]+,\s+)", text)
    patent_display = title_match.group(1).replace(",", "") if title_match else item["number"]
    title = title_match.group(2).strip(" .") if title_match else ""
    latin_name = extract_between(text, "Latin Name:", r"Varietal Denomination:|Assigned to|Filed by|Filed on")
    cultivar = extract_between(text, "Varietal Denomination:", r"Assigned to|Filed by|Filed on|Int\. Cl\.")
    assignee = extract_between(text, "Assigned to", r"Filed by|Filed on|Int\. Cl\.")
    filed_by = extract_between(text, "Filed by", r"Filed on|Int\. Cl\.")
    app_match = re.search(r"Filed on\s+(.*?),\s+as Appl\. No\.\s+([0-9/,]+)", text)
    filed_date = app_match.group(1).strip() if app_match else ""
    application_number = app_match.group(2).strip() if app_match else ""
    crop = classify_crop(" ".join([title, latin_name, cultivar, text]), keywords)

    if not crop:
        return None

    return {
        "id": patent_display,
        "source": "USPTO Official Gazette",
        "sourceKind": "Issued plant patent",
        "primarySource": patent_display,
        "patentNumber": patent_display,
        "publicationNumber": "",
        "applicationNumber": application_number,
        "date": item["issueDate"],
        "issueDate": item["issueDate"],
        "filedDateText": filed_date,
        "title": title,
        "crop": crop,
        "cultivar": cultivar,
        "tradeName": "",
        "status": "issued",
        "breeders": "",
        "assignee": assignee or filed_by,
        "inventors": "",
        "list": "",
        "notes": latin_name,
        "sourceUrl": item["detailUrl"],
        "detailText": text[:1500],
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


def load_payload() -> dict[str, Any]:
    if DATA_PATH.exists():
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return {"metadata": {}, "records": []}


def save_payload(payload: dict[str, Any]) -> None:
    payload["records"].sort(key=lambda row: row.get("date") or "", reverse=True)
    payload["metadata"]["generatedAt"] = datetime.now(timezone.utc).isoformat()
    payload["metadata"]["recordCount"] = len(payload["records"])
    DATA_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def refresh(issue_limit: int) -> int:
    keywords = load_keywords()
    payload = load_payload()
    records = payload.setdefault("records", [])
    existing_ids = {row.get("id") for row in records}
    added = 0
    checked = 0

    for issue in find_issues(issue_limit):
        for item in parse_issue(issue):
            checked += 1
            if item["number"] in existing_ids or "US" + item["number"] in existing_ids:
                continue
            record = parse_patent_detail(item, keywords)
            if record:
                records.append(record)
                existing_ids.add(record["id"])
                added += 1

    payload.setdefault("metadata", {})["lastGrantRefresh"] = datetime.now(timezone.utc).isoformat()
    payload["metadata"]["lastGrantRefreshChecked"] = checked
    payload["metadata"]["lastGrantRefreshAdded"] = added
    payload["metadata"].setdefault("sources", [])
    if "USPTO Official Gazette public plant patent pages" not in payload["metadata"]["sources"]:
        payload["metadata"]["sources"].append("USPTO Official Gazette public plant patent pages")
    save_payload(payload)
    print(f"Checked {checked} Gazette plant patents; added {added} target crop records.")
    return added


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh public USPTO plant patent grants from the Official Gazette.")
    parser.add_argument("--issues", type=int, default=8, help="Number of recent Gazette issues to scan.")
    args = parser.parse_args()
    refresh(max(1, args.issues))


if __name__ == "__main__":
    main()
