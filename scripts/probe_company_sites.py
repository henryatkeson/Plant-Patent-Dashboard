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
LINKEDIN_HOSTS = {"linkedin.com", "www.linkedin.com"}

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


def hostname(url: str) -> str:
    return urllib.parse.urlparse(url).hostname or ""


def is_linkedin_url(url: str) -> bool:
    return hostname(url).lower() in LINKEDIN_HOSTS


def probe_url(url: str, *, skip_linkedin: bool = False) -> dict[str, Any]:
    url = clean_text(url)
    if not url:
        return {
            "url": "",
            "ok": False,
            "status": "",
            "finalUrl": "",
            "error": "No URL",
            "title": "",
            "html": "",
            "checkType": "missing",
        }
    if skip_linkedin and is_linkedin_url(url):
        parsed = urllib.parse.urlparse(url)
        return {
            "url": url,
            "ok": bool(parsed.path.strip("/")),
            "status": "not fetched",
            "finalUrl": url,
            "error": "LinkedIn blocks many automated checks; manual browser QA required.",
            "title": "",
            "html": "",
            "checkType": "linkedin_url_format",
        }
    response = safe_fetch(url)
    html = response.pop("html", "")
    return {
        "url": url,
        "ok": response["ok"],
        "status": response["status"],
        "finalUrl": response["finalUrl"],
        "error": response["error"],
        "title": html_title(html),
        "html": html,
        "checkType": "http",
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
    contact_url = clean_text(profile.get("contactUrl"))
    source_url = clean_text(profile.get("sourceUrl"))
    linkedin_url = clean_text(profile.get("linkedinUrl"))
    news_links = profile.get("newsLinks") or []
    response = probe_url(website)
    html = response.pop("html", "")
    lowered = html.lower()
    keyword_counts = {keyword: lowered.count(keyword) for keyword in KEYWORDS if lowered.count(keyword)}
    contact_response = probe_url(contact_url) if contact_url else probe_url("")
    contact_response.pop("html", None)
    source_response = probe_url(source_url) if source_url and source_url != website else {
        "url": source_url,
        "ok": bool(source_url) and response["ok"],
        "status": response["status"] if source_url else "",
        "finalUrl": response["finalUrl"] if source_url else "",
        "error": "" if source_url and response["ok"] else ("No URL" if not source_url else response["error"]),
        "title": response["title"] if source_url else "",
        "checkType": "same_as_website" if source_url else "missing",
    }
    source_response.pop("html", None)
    linkedin_response = probe_url(linkedin_url, skip_linkedin=True) if linkedin_url else probe_url("")
    linkedin_response.pop("html", None)
    news_responses = []
    for link in news_links:
        label = clean_text(link.get("label"))
        url = clean_text(link.get("url"))
        news_response = probe_url(url)
        news_response.pop("html", None)
        news_response["label"] = label
        news_responses.append(news_response)
    flags = []
    if not website:
        flags.append("missing_website")
    elif not response["ok"]:
        flags.append("website_failed")
    if not contact_url:
        flags.append("missing_contact_url")
    elif not contact_response["ok"]:
        flags.append("contact_failed")
    if not linkedin_url:
        flags.append("missing_linkedin_url")
    elif linkedin_response["checkType"] == "linkedin_url_format":
        flags.append("linkedin_manual_check_required")
    if not source_url:
        flags.append("missing_source_url")
    elif not source_response["ok"]:
        flags.append("source_failed")
    news_failures = [item for item in news_responses if not item["ok"]]
    if news_failures:
        flags.append("news_failed")
    if not flags:
        qa_status = "verified"
    elif not website or not response["ok"]:
        qa_status = "unresolved"
    elif any(flag.endswith("_failed") for flag in flags):
        qa_status = "needs_fix"
    else:
        qa_status = "verified_with_gaps"
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
        "contact": contact_response,
        "source": source_response,
        "linkedin": linkedin_response,
        "news": news_responses,
        "qaStatus": qa_status,
        "auditFlags": flags,
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
        "contactUrl": row["contact"]["url"],
        "contactOk": row["contact"]["ok"],
        "contactStatus": row["contact"]["status"],
        "contactFinalUrl": row["contact"]["finalUrl"],
        "contactError": row["contact"]["error"],
        "sourceUrl": row["source"]["url"],
        "sourceOk": row["source"]["ok"],
        "sourceStatus": row["source"]["status"],
        "sourceFinalUrl": row["source"]["finalUrl"],
        "sourceError": row["source"]["error"],
        "linkedinUrl": row["linkedin"]["url"],
        "linkedinOk": row["linkedin"]["ok"],
        "linkedinStatus": row["linkedin"]["status"],
        "linkedinError": row["linkedin"]["error"],
        "newsLinksChecked": len(row["news"]),
        "newsLinksOkCount": sum(1 for link in row["news"] if link["ok"]),
        "newsLinksFailed": " | ".join(
            f"{link.get('label') or 'link'} <{link.get('url')}>: {link.get('error') or link.get('status')}"
            for link in row["news"]
            if not link["ok"]
        ),
        "qaStatus": row["qaStatus"],
        "auditFlags": " | ".join(row["auditFlags"]),
        "probedAt": row["probedAt"],
    }


def main() -> int:
    profiles = read_json(COMPANY_PROFILE_PATH)
    rows = [probe_company(profile) for profile in profiles if clean_text(profile.get("canonicalName"))]
    payload = {
        "summary": {
            "profileCount": len(rows),
            "websiteVerifiedCount": sum(1 for row in rows if row["ok"]),
            "websiteMissingCount": sum(1 for row in rows if not row["website"]),
            "websiteFailedCount": sum(1 for row in rows if row["website"] and not row["ok"]),
            "contactUrlCount": sum(1 for row in rows if row["contact"]["url"]),
            "contactVerifiedCount": sum(1 for row in rows if row["contact"]["url"] and row["contact"]["ok"]),
            "linkedinUrlCount": sum(1 for row in rows if row["linkedin"]["url"]),
            "newsLinkCount": sum(len(row["news"]) for row in rows),
            "newsLinkVerifiedCount": sum(sum(1 for link in row["news"] if link["ok"]) for row in rows),
            "qaStatusCounts": {
                status: sum(1 for row in rows if row["qaStatus"] == status)
                for status in sorted({row["qaStatus"] for row in rows})
            },
        },
        "metadata": {
            "title": "Company Website Probe",
            "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
            "profileCount": len(rows),
            "methodNotes": [
                "This validates public website, contact, source, and news-link availability and finds likely cultivar/variety evidence links.",
                "Keyword counts are page-level hints, not cultivar counts.",
                "LinkedIn URLs are syntax-checked only because LinkedIn often blocks automated checks; manual browser QA is still required.",
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
