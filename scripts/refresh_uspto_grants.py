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


def title_case_crop(value: str) -> str:
    parts = re.split(r"([-\u2013\u2014/() ])", value or "")
    small_words = {"and", "or", "of", "the", "in"}
    titled = []
    for part in parts:
        if re.fullmatch(r"[A-Za-z]+", part):
            lower = part.lower()
            titled.append(lower if lower in small_words else lower[:1].upper() + lower[1:])
        else:
            titled.append(part)
    return "".join(titled).strip()


def crop_from_title(title: str) -> str:
    match = re.search(r"^(.+?)\s+plant\s+named\b", title or "", re.I)
    if match:
        return title_case_crop(match.group(1).strip())
    first = (title or "").split(" ", 1)[0].strip(" ,.;:")
    return title_case_crop(first or "Other Plant")


def cultivar_from_title(title: str) -> str:
    match = re.search(r"named\s+[\u2018'\"\u201c](.+?)[\u2019'\"\u201d]", title or "", re.I)
    return match.group(1).strip() if match else ""


def parse_patent_detail(item: dict[str, str], keywords: list[str]) -> dict[str, Any] | None:
    detail = fetch_patent_detail(item)
    if not detail:
        return None

    classified_crop = classify_crop(" ".join([detail["title"], detail["latin_name"], detail["cultivar"], detail["text"]]), keywords)
    crop = title_case_crop(classified_crop) if classified_crop else crop_from_title(detail["title"])

    return {
        "id": detail["patent_display"],
        "source": "USPTO Official Gazette",
        "sourceKind": "Issued plant patent",
        "primarySource": detail["patent_display"],
        "patentNumber": detail["patent_display"],
        "publicationNumber": "",
        "applicationNumber": detail["application_number"],
        "date": item["issueDate"],
        "issueDate": item["issueDate"],
        "filedDateText": detail["filed_date"],
        "title": detail["title"],
        "crop": crop,
        "cropFocus": "Target crop" if classified_crop else "Other plant patent",
        "cultivar": detail["cultivar"],
        "tradeName": "",
        "status": "issued",
        "breeders": "",
        "assignee": detail["assignee"] or detail["filed_by"],
        "inventors": detail["inventors"],
        "list": "",
        "notes": detail["latin_name"],
        "sourceUrl": item["detailUrl"],
        "detailText": detail["text"][:1500],
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


def fetch_patent_detail(item: dict[str, str]) -> dict[str, str] | None:
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
    title_cultivar = cultivar_from_title(title)
    if title_cultivar and (not cultivar or len(cultivar) > len(title_cultivar) + 8):
        cultivar = title_cultivar
    assignee = extract_between(text, "Assigned to", r"Filed by|Filed on|Int\. Cl\.")
    filed_by = extract_between(text, "Filed by", r"Filed on|Int\. Cl\.")
    app_match = re.search(r"Filed on\s+(.*?),\s+as Appl\. No\.\s+([0-9/,]+)", text)
    filed_date = app_match.group(1).strip() if app_match else ""
    application_number = app_match.group(2).strip() if app_match else ""
    inventors = extract_inventors(text, title, latin_name, cultivar)
    return {
        "text": text,
        "patent_display": patent_display,
        "title": title,
        "latin_name": latin_name,
        "cultivar": cultivar,
        "assignee": assignee,
        "filed_by": filed_by,
        "filed_date": filed_date,
        "application_number": application_number,
        "inventors": inventors,
    }


def extract_inventors(text: str, title: str, latin_name: str, cultivar: str) -> str:
    anchors = [cultivar, latin_name, title]
    start_idx = -1
    for anchor in anchors:
        if anchor:
            start_idx = text.find(anchor)
            if start_idx >= 0:
                start_idx += len(anchor)
                break
    if start_idx < 0:
        return ""
    tail = text[start_idx:]
    end = re.search(r"\s+Assigned to|\s+Filed by|\s+Filed on|\s+Int\. Cl\.", tail)
    return tail[: end.start()].strip(" .,;") if end else ""


def load_payload() -> dict[str, Any]:
    if DATA_PATH.exists():
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return {"metadata": {}, "records": []}


def save_payload(payload: dict[str, Any]) -> None:
    payload["records"].sort(key=lambda row: row.get("date") or "", reverse=True)
    payload["metadata"]["generatedAt"] = datetime.now(timezone.utc).isoformat()
    payload["metadata"]["recordCount"] = len(payload["records"])
    DATA_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def patent_key(value: str) -> str:
    match = re.search(r"\b(?:US)?PP\s*0*([0-9,]+)\b|\b(?:US)?PP0*([0-9]{5,6})\b", value or "", re.I)
    if not match:
        return ""
    number = (match.group(1) or match.group(2) or "").replace(",", "")
    return f"PP{int(number):06d}" if number.isdigit() else ""


def merge_detail(row: dict[str, Any], item: dict[str, str], detail: dict[str, str]) -> bool:
    changed = False
    updates = {
        "sourceUrl": item["detailUrl"],
        "verifiedSource": "USPTO Official Gazette",
        "verifiedAt": datetime.now(timezone.utc).isoformat(),
        "applicationNumber": detail["application_number"],
        "filedDateText": detail["filed_date"],
        "detailText": detail["text"][:1500],
    }
    if detail["assignee"]:
        updates["assignee"] = detail["assignee"]
    if detail["inventors"]:
        updates["inventors"] = detail["inventors"]
    if detail["title"] and not row.get("title"):
        updates["title"] = detail["title"]
    if detail["cultivar"] and not row.get("cultivar"):
        updates["cultivar"] = detail["cultivar"]
    if detail["latin_name"] and not row.get("notes"):
        updates["notes"] = detail["latin_name"]

    for key, value in updates.items():
        if value and row.get(key) != value:
            row[key] = value
            changed = True
    return changed


def refresh(issue_limit: int) -> int:
    keywords = load_keywords()
    payload = load_payload()
    records = payload.setdefault("records", [])
    existing_ids = {row.get("id") for row in records}
    rows_by_patent: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        key = patent_key(" ".join([str(row.get("primarySource") or ""), str(row.get("patentNumber") or ""), str(row.get("id") or "")]))
        if key:
            rows_by_patent.setdefault(key, []).append(row)
    added = 0
    enriched = 0
    checked = 0

    for issue in find_issues(issue_limit):
        for item in parse_issue(issue):
            checked += 1
            matching_rows = rows_by_patent.get(item["number"], [])
            if matching_rows:
                if all(row.get("sourceUrl") for row in matching_rows):
                    continue
                detail = fetch_patent_detail(item)
                if not detail:
                    continue
                for row in matching_rows:
                    if merge_detail(row, item, detail):
                        enriched += 1
                continue
            if item["number"] in existing_ids or "US" + item["number"] in existing_ids:
                continue
            record = parse_patent_detail(item, keywords)
            if record:
                records.append(record)
                existing_ids.add(record["id"])
                rows_by_patent.setdefault(item["number"], []).append(record)
                added += 1

    payload.setdefault("metadata", {})["lastGrantRefresh"] = datetime.now(timezone.utc).isoformat()
    payload["metadata"]["lastGrantRefreshChecked"] = checked
    payload["metadata"]["lastGrantRefreshAdded"] = added
    payload["metadata"]["lastGrantRefreshEnriched"] = enriched
    payload["metadata"].setdefault("sources", [])
    if "USPTO Official Gazette public plant patent pages" not in payload["metadata"]["sources"]:
        payload["metadata"]["sources"].append("USPTO Official Gazette public plant patent pages")
    save_payload(payload)
    print(f"Checked {checked} Gazette plant patents; added {added} plant patent records; enriched {enriched} existing records.")
    return added


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh public USPTO plant patent grants from the Official Gazette.")
    parser.add_argument("--issues", type=int, default=8, help="Number of recent Gazette issues to scan.")
    args = parser.parse_args()
    refresh(max(1, args.issues))


if __name__ == "__main__":
    main()
