import math
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time as dt_time, timezone, timedelta
from io import BytesIO

import feedparser
import requests
from tqdm import tqdm
from dateutil import parser as dtparser
from dotenv import load_dotenv
from tocify.frontmatter import aggregate_ranked_item_tags, with_frontmatter
from tocify.utils import sha1

load_dotenv()

# ---- config (env-tweakable) ----
MAX_ITEMS_PER_FEED = int(os.getenv("MAX_ITEMS_PER_FEED", "50"))
MAX_TOTAL_ITEMS = int(os.getenv("MAX_TOTAL_ITEMS", "400"))
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "7"))
INTERESTS_MAX_CHARS = int(os.getenv("INTERESTS_MAX_CHARS", "3000"))
SUMMARY_MAX_CHARS = int(os.getenv("SUMMARY_MAX_CHARS", "500"))
PREFILTER_KEEP_TOP = int(os.getenv("PREFILTER_KEEP_TOP", "200"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "50"))
MIN_SCORE_READ = float(os.getenv("MIN_SCORE_READ", "0.65"))
MAX_RETURNED = int(os.getenv("MAX_RETURNED", "40"))
RSS_FETCH_TIMEOUT = int(os.getenv("RSS_FETCH_TIMEOUT", "25"))


# ---- tiny helpers ----
def load_feeds(path: str) -> list[dict]:
    """
    Supports:
    - blank lines
    - comments starting with #
    - optional naming via: Name | URL

    Returns list of:
    { "name": "...", "url": "..." }
    """
    feeds = []

    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue

            # Named feed: "Name | URL"
            if "|" in s:
                name, url = [x.strip() for x in s.split("|", 1)]
            else:
                name, url = None, s

            feeds.append({
                "name": name,
                "url": url
            })

    return feeds

def read_text(path: str) -> str:
    """Read and return the entire contents of a text file."""
    with open(path, encoding="utf-8") as f:
        return f.read()


def section(md: str, heading: str) -> str:
    """Extract the first markdown section body under the given heading (e.g. ## Keywords)."""
    m = re.search(rf"(?im)^\s*#{1,6}\s+{re.escape(heading)}\s*$", md)
    if not m:
        return ""
    rest = md[m.end():]
    m2 = re.search(r"(?im)^\s*#{1,6}\s+\S", rest)
    return (rest[:m2.start()] if m2 else rest).strip()

def parse_interests_md(md: str) -> dict:
    """Parse interests markdown with Keywords, Narrative, and optional Companies sections.
    Returns dict with keys: keywords (list), narrative (str, truncated), companies (list, optional)."""
    keywords = []
    for line in section(md, "Keywords").splitlines():
        line = re.sub(r"^[\-\*\+]\s+", "", line.strip())
        if line:
            keywords.append(line)
    narrative = section(md, "Narrative").strip()
    if len(narrative) > INTERESTS_MAX_CHARS:
        narrative = narrative[:INTERESTS_MAX_CHARS] + "…"
    companies = []
    for line in section(md, "Companies").splitlines():
        line = re.sub(r"^[\-\*\+]\s+", "", line.strip())
        if line:
            companies.append(line)
    return {
        "keywords": keywords[:200],
        "narrative": narrative,
        "companies": companies[:200],
    }


def topic_search_string(
    interests: dict,
    max_keywords: int | None = None,
    *,
    narrative_fallback_words: int = 15,
) -> str:
    """Build a single search string from interests keywords for OpenAlex/NewsAPI queries.
    Uses all keywords (or first max_keywords if set) joined by spaces.
    When there are no keywords and narrative_fallback_words > 0, uses the first N words of the narrative as fallback."""
    keywords = interests.get("keywords") or []
    if max_keywords is not None:
        keywords = keywords[:max_keywords]
    taken = [k.strip() for k in keywords if k and str(k).strip()]
    if taken:
        return " ".join(taken)
    if narrative_fallback_words <= 0:
        return ""
    narrative = (interests.get("narrative") or "").strip()
    if not narrative:
        return ""
    words = re.findall(r"\b\w+\b", narrative)
    first = words[:narrative_fallback_words]
    return " ".join(first) if first else ""


def topic_search_queries(
    interests: dict,
    max_queries: int | None = None,
) -> list[str]:
    """Build a list of search queries from interests keywords (one per keyword).
    Returns all non-empty, stripped keywords; if max_queries is set (e.g. 100), cap at that for safety.
    Used by Google News to run one RSS search per keyword so no topic is left out."""
    keywords = interests.get("keywords") or []
    taken = [k.strip() for k in keywords if k and str(k).strip()]
    if max_queries is not None and max_queries > 0:
        taken = taken[:max_queries]
    return taken


# ---- rss ----
def parse_date(entry) -> datetime | None:
    """Return datetime (UTC) for an RSS entry from published/updated fields, or None."""
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    for key in ("published", "updated", "created"):
        val = entry.get(key)
        if val:
            try:
                dt = dtparser.parse(val)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def _fetch_one_feed(
    feed: dict,
    cutoff: datetime,
    end_dt: datetime,
    timeout: int,
) -> list[dict]:
    """Fetch one feed URL and return list of item dicts; on error return [] and log."""
    url = feed["url"]
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        d = feedparser.parse(BytesIO(resp.content))
    except Exception as e:
        tqdm.write(f"[WARN] RSS fetch failed {url!r}: {e}")
        return []
    source = (
        feed.get("name")
        or (d.feed.get("title") if d.feed else None)
        or url
    )
    source = (source or "").strip()
    items: list[dict] = []
    for e in d.entries[:MAX_ITEMS_PER_FEED]:
        title = (e.get("title") or "").strip()
        link = (e.get("link") or "").strip()
        if not (title and link):
            continue
        dt = parse_date(e)
        if dt and (dt < cutoff or dt > end_dt):
            continue
        summary = re.sub(r"\s+", " ", (e.get("summary") or e.get("description") or "").strip())
        if len(summary) > SUMMARY_MAX_CHARS:
            summary = summary[:SUMMARY_MAX_CHARS] + "…"
        items.append({
            "id": sha1(f"{source}|{title}|{link}"),
            "source": source,
            "title": title,
            "link": link,
            "published_utc": dt.isoformat() if dt else None,
            "summary": summary,
        })
    return items


def fetch_rss_items(feeds: list[dict], end_date: date | None = None) -> list[dict]:
    """Fetch RSS items. If end_date is None, use now; else window ends at end_date 23:59:59 UTC."""
    if end_date is None:
        end_dt = datetime.now(timezone.utc)
        cutoff = end_dt - timedelta(days=LOOKBACK_DAYS)
    else:
        end_dt = datetime.combine(end_date, dt_time(23, 59, 59), tzinfo=timezone.utc)
        cutoff = end_dt - timedelta(days=LOOKBACK_DAYS)
    if not feeds:
        return []
    timeout = RSS_FETCH_TIMEOUT
    max_workers = min(
        int(os.getenv("RSS_FETCH_MAX_WORKERS", "10")),
        len(feeds),
    )
    max_workers = max(1, max_workers)
    items: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(_fetch_one_feed, feed, cutoff, end_dt, timeout)
            for feed in feeds
        ]
        for fut in futures:
            try:
                items.extend(fut.result())
            except Exception as e:
                tqdm.write(f"[WARN] RSS fetch task failed: {e}")
    # dedupe + newest first
    items = list({it["id"]: it for it in items}.values())
    items.sort(key=lambda x: x["published_utc"] or "", reverse=True)
    return items[:MAX_TOTAL_ITEMS]


def merge_feed_items(*item_lists: list[dict], max_items: int | None = None) -> list[dict]:
    """Merge multiple lists of feed items (same schema: id, source, title, link, published_utc, summary). Dedupe by id, sort newest first."""
    seen: dict[str, dict] = {}
    for lst in item_lists:
        for it in lst:
            iid = it.get("id")
            if iid and iid not in seen:
                seen[iid] = it
    out = sorted(seen.values(), key=lambda x: x.get("published_utc") or "", reverse=True)
    if max_items is not None:
        out = out[:max_items]
    return out


# ---- local prefilter ----
def keyword_prefilter(
    items: list[dict],
    keywords: list[str],
    keep_top: int,
    *,
    companies: list[str] | None = None,
) -> list[dict]:
    """Score items by keyword and company hits; return top keep_top (or unfiltered slice if few matches).
    If companies is provided, matches on company names count toward the score like keyword matches."""
    kws = [k.lower() for k in keywords if k.strip()]
    comps = [c.lower() for c in (companies or []) if c.strip()]
    all_terms = kws + comps

    def hits(it):
        text = (it.get("title", "") + " " + it.get("summary", "")).lower()
        return sum(1 for t in all_terms if t in text)

    scored = [(hits(it), it) for it in items]
    matched = [it for s, it in scored if s > 0]
    if len(matched) < min(50, keep_top):
        return items[:keep_top]
    matched.sort(key=hits, reverse=True)
    return matched[:keep_top]


# ---- triage (backend-agnostic batch loop) ----
def triage_in_batches(
    interests: dict,
    items: list[dict],
    batch_size: int,
    triage_fn,
    progress_disable: bool | None = None,
) -> dict:
    """triage_fn(interests, batch) -> dict with keys notes, ranked (and optionally week_of)."""
    week_of = datetime.now(timezone.utc).date().isoformat()
    total = math.ceil(len(items) / batch_size)
    all_ranked, notes_parts = [], []
    disable = progress_disable if progress_disable is not None else not sys.stderr.isatty()

    batch_starts = range(0, len(items), batch_size)
    with tqdm(batch_starts, desc="Triage", unit="batch", total=total, disable=disable) as pbar:
        for i in pbar:
            batch = items[i : i + batch_size]
            batch_num = i // batch_size + 1
            pbar.set_postfix_str(f"batch {batch_num}/{total}, {len(batch)} items")
            res = triage_fn(interests, batch)
            if res.get("notes", "").strip():
                notes_parts.append(res["notes"].strip())
            all_ranked.extend(res.get("ranked", []))

    best = {}
    for r in all_ranked:
        rid = r["id"]
        if rid not in best or r["score"] > best[rid]["score"]:
            best[rid] = r

    ranked = sorted(best.values(), key=lambda x: x["score"], reverse=True)
    return {"week_of": week_of, "notes": " ".join(dict.fromkeys(notes_parts))[:1000], "ranked": ranked}


# ---- render ----
def render_digest_md(result: dict, items_by_id: dict[str, dict]) -> str:
    """Render triage result and items_by_id to markdown with YAML frontmatter."""
    week_of = result["week_of"]
    notes = result.get("notes", "").strip()
    ranked = result.get("ranked", [])
    kept = [r for r in ranked if r["score"] >= MIN_SCORE_READ][:MAX_RETURNED]
    today = datetime.now(timezone.utc).date().isoformat()
    title = f"Weekly ToC Digest (week of {week_of})"
    triage_backend = str(result.get("triage_backend") or "unknown")
    triage_model = str(result.get("triage_model") or "unknown")

    lines = [f"# {title}", ""]
    if notes:
        lines += [notes, ""]
    lines += [
        f"**Included:** {len(kept)} (score ≥ {MIN_SCORE_READ:.2f})  ",
        f"**Scored:** {len(ranked)} total items",
        "",
        "---",
        "",
    ]
    if not kept:
        return "\n".join(lines + ["_No items met the relevance threshold this week._", ""])

    for r in kept:
        it = items_by_id.get(r["id"], {})
        tags = ", ".join(r.get("tags", [])) if r.get("tags") else ""
        pub = r.get("published_utc")
        summary = (it.get("summary") or "").strip()

        lines += [
            f"## [{r['title']}]({r['link']})",
            f"*{r['source']}*  ",
            f"Score: **{r['score']:.2f}**" + (f"  \nPublished: {pub}" if pub else ""),
            (f"Tags: {tags}" if tags else ""),
            "",
            r["why"].strip(),
            "",
        ]
        if summary:
            lines += ["<details>", "<summary>RSS summary</summary>", "", summary, "", "</details>", ""]
        lines += ["---", ""]
    body = "\n".join(lines)
    frontmatter = {
        "title": title,
        "date": week_of,
        "lastmod": today,
        "tags": aggregate_ranked_item_tags(kept if kept else ranked),
        "generator": "tocify-digest",
        "period": "weekly",
        "week_of": week_of,
        "included": len(kept),
        "scored": len(ranked),
        "triage_backend": triage_backend,
        "triage_model": triage_model,
    }
    return with_frontmatter(body, frontmatter)


def main():
    """Run the single-topic pipeline: interests.md, feeds.txt -> digest.md. Respects env (backend, limits)."""
    interests = parse_interests_md(read_text("interests.md"))
    feeds = load_feeds("feeds.txt")
    items = fetch_rss_items(feeds)
    print(f"Fetched {len(items)} RSS items (pre-filter)")

    # Optional news backend for present flow (same date window as RSS)
    now = datetime.now(timezone.utc)
    start_dt = now - timedelta(days=LOOKBACK_DAYS)
    end_dt = now
    news_backend = (os.getenv("NEWS_BACKEND") or "").strip().lower()
    add_google_news = (os.getenv("ADD_GOOGLE_NEWS") or "").strip().lower() in ("1", "true", "yes")
    if news_backend == "newsapi":
        try:
            from tocify.news import fetch_news_items as fetch_news
            news_items = fetch_news(start_dt.date(), end_dt.date())
            if news_items:
                items = merge_feed_items(items, news_items, max_items=MAX_TOTAL_ITEMS)
                print(f"Added {len(news_items)} news items (merged total {len(items)})")
        except Exception as e:
            tqdm.write(f"[WARN] News backend failed: {e}")
    if add_google_news or news_backend == "googlenews":
        try:
            from tocify.googlenews import fetch_google_news_items
            queries = topic_search_queries(interests)
            if queries:
                gnews_items = fetch_google_news_items(start_dt.date(), end_dt.date(), queries)
                if gnews_items:
                    items = merge_feed_items(items, gnews_items, max_items=MAX_TOTAL_ITEMS)
                    print(f"Added {len(gnews_items)} Google News items (merged total {len(items)})")
        except Exception as e:
            tqdm.write(f"[WARN] Google News fetch failed: {e}")
    triage_metadata = {"triage_backend": "unknown", "triage_model": "unknown"}
    try:
        from tocify.integrations import get_triage_runtime_metadata

        triage_metadata = get_triage_runtime_metadata()
    except Exception:
        pass

    today = datetime.now(timezone.utc).date().isoformat()
    if not items:
        no_items_body = (
            f"# Weekly ToC Digest (week of {today})\n\n"
            f"_No RSS items found in the last {LOOKBACK_DAYS} days._\n"
        )
        no_items_frontmatter = {
            "title": f"Weekly ToC Digest (week of {today})",
            "date": today,
            "lastmod": today,
            "tags": [],
            "generator": "tocify-digest",
            "period": "weekly",
            "week_of": today,
            "included": 0,
            "scored": 0,
            "triage_backend": triage_metadata["triage_backend"],
            "triage_model": triage_metadata["triage_model"],
        }
        with open("digest.md", "w", encoding="utf-8") as f:
            f.write(with_frontmatter(no_items_body, no_items_frontmatter))
        print("No items; wrote digest.md")
        return

    items = keyword_prefilter(
        items,
        interests["keywords"],
        keep_top=PREFILTER_KEEP_TOP,
        companies=interests.get("companies", []),
    )
    print(f"Sending {len(items)} RSS items to model (post-filter)")

    items_by_id = {it["id"]: it for it in items}

    from tocify.integrations import get_triage_backend_with_metadata
    triage_fn, triage_metadata = get_triage_backend_with_metadata()
    result = triage_in_batches(interests, items, BATCH_SIZE, triage_fn)
    result["triage_backend"] = triage_metadata["triage_backend"]
    result["triage_model"] = triage_metadata["triage_model"]
    md = render_digest_md(result, items_by_id)

    with open("digest.md", "w", encoding="utf-8") as f:
        f.write(md)
    print("Wrote digest.md")


if __name__ == "__main__":
    main()
