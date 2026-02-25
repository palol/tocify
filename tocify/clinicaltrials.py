"""
ClinicalTrials.gov backend: fetch studies by date range. Same item schema as RSS
(id, source, title, link, published_utc, summary). Uses API v2.
"""

import os
from datetime import date, datetime, timezone

import requests
from dotenv import load_dotenv

from tocify.utils import normalize_summary, sha1

load_dotenv()

SUMMARY_MAX_CHARS = int(os.getenv("SUMMARY_MAX_CHARS", "500"))
CLINICALTRIALS_TIMEOUT = int(os.getenv("CLINICALTRIALS_TIMEOUT", "30"))
CLINICALTRIALS_PAGE_SIZE = min(100, max(1, int(os.getenv("CLINICALTRIALS_PAGE_SIZE", "100"))))
CLINICALTRIALS_MAX_ITEMS = int(os.getenv("CLINICALTRIALS_MAX_ITEMS", "200"))

CLINICALTRIALS_API_V2 = "https://clinicaltrials.gov/api/v2/studies"


def fetch_clinicaltrials_items(
    start_date: date,
    end_date: date,
    *,
    query: str | None = None,
) -> list[dict]:
    """
    Fetch studies from ClinicalTrials.gov API v2 for the given date range.
    Returns list of dicts with keys: id, source, title, link, published_utc, summary
    (same schema as RSS items for merge/triage).

    Date filtering is done client-side using lastUpdatePostDate. Optional query
    filters by condition/keyword via API when provided.
    """
    start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)

    params: dict = {
        "pageSize": CLINICALTRIALS_PAGE_SIZE,
    }
    if query and query.strip():
        params["query.term"] = query.strip()[:500]

    items: list[dict] = []
    page_token: str | None = None

    while len(items) < CLINICALTRIALS_MAX_ITEMS:
        if page_token:
            params["pageToken"] = page_token
        try:
            resp = requests.get(
                CLINICALTRIALS_API_V2,
                params=params,
                timeout=CLINICALTRIALS_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            if not items:
                import warnings
                warnings.warn(f"ClinicalTrials.gov fetch failed: {e}", stacklevel=2)
            break

        studies = data.get("studies") or []
        next_page_token = data.get("nextPageToken")

        for study in studies:
            if len(items) >= CLINICALTRIALS_MAX_ITEMS:
                break
            try:
                protocol = study.get("protocolSection") or {}
                ident = protocol.get("identificationModule") or {}
                status = protocol.get("statusModule") or {}
                desc = protocol.get("descriptionModule") or {}

                nct_id = (ident.get("nctId") or "").strip()
                if not nct_id:
                    continue
                title = (ident.get("briefTitle") or ident.get("officialTitle") or nct_id).strip()
                link = f"https://clinicaltrials.gov/study/{nct_id}"

                last_post = status.get("lastUpdatePostDateStruct") or {}
                date_str = (last_post.get("date") or "").strip()
                if not date_str:
                    continue
                try:
                    if len(date_str) == 7:
                        dt = datetime.strptime(date_str, "%Y-%m").replace(
                            tzinfo=timezone.utc
                        )
                    else:
                        dt = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(
                            tzinfo=timezone.utc
                        )
                    if dt < start_dt or dt > end_dt:
                        continue
                    published_utc = dt.isoformat()
                except Exception:
                    continue

                summary = normalize_summary(
                    desc.get("briefSummary") or desc.get("detailedDescription") or "",
                    max_chars=SUMMARY_MAX_CHARS,
                )
                source_name = "ClinicalTrials.gov"
                item_id = sha1(f"{source_name}|{title}|{link}")
                items.append({
                    "id": item_id,
                    "source": source_name,
                    "title": title,
                    "link": link,
                    "published_utc": published_utc,
                    "summary": summary,
                })
            except Exception:
                continue

        if not next_page_token or not studies:
            break
        page_token = next_page_token

    items.sort(key=lambda x: x.get("published_utc") or "", reverse=True)
    return items
