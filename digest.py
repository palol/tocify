import os, re, math, hashlib, shlex, logging
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin, urlparse

import feedparser
from dateutil import parser as dtparser
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("tocify")
if not log.handlers:
    logging.basicConfig(level=os.getenv("TOCIFY_LOG_LEVEL", "INFO"), format="%(levelname)s %(name)s: %(message)s")

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

# HTML adapter (PR #1: opt-in via flag; flips default-on in PR #2)
ENABLE_HTML = os.getenv("TOCIFY_ENABLE_HTML", "0") in ("1", "true", "True", "yes")
HTML_TIMEOUT = float(os.getenv("TOCIFY_HTML_TIMEOUT", "20"))
HTML_USER_AGENT = os.getenv(
    "TOCIFY_HTML_USER_AGENT",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
)


# ---- tiny helpers ----
def _parse_selector_kwargs(rest: str) -> dict:
    """
    Parse `key="value" key2=value2` into a dict using shell-style quoting.
    Returns {} on parse failure (with a warning).
    """
    out = {}
    try:
        tokens = shlex.split(rest)
    except ValueError as e:
        log.warning("feeds.txt: could not parse selector args %r: %s", rest, e)
        return out
    for tok in tokens:
        if "=" not in tok:
            log.warning("feeds.txt: ignoring selector token without '=': %r", tok)
            continue
        k, v = tok.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def load_feeds(path: str) -> list[dict]:
    """
    Supports:
    - blank lines
    - comments starting with #
    - optional naming via: Name | URL
    - optional source type + selectors via: Name | URL | TYPE [k=v ...]
        TYPE is currently 'rss' (default) or 'html'.
        For 'html', selector keys: item, title, link, date, summary.
        Each value is a CSS selector, optionally with `@attr` to pull an
        attribute instead of text content (e.g., `time@datetime`, `a@href`).

    Returns list of:
    { "name": str|None, "url": str, "type": "rss"|"html", "selectors": dict }
    """
    feeds = []

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue

            # Split on "|" into up to 3 fields: Name | URL | TYPE [selectors]
            parts = [p.strip() for p in s.split("|", 2)]
            if len(parts) == 1:
                name, url, third = None, parts[0], ""
            elif len(parts) == 2:
                name, url, third = parts[0], parts[1], ""
            else:
                name, url, third = parts[0], parts[1], parts[2]

            ftype = "rss"
            selectors: dict = {}
            if third:
                tparts = third.split(None, 1)
                ftype = tparts[0].lower()
                if ftype not in ("rss", "html"):
                    log.warning("feeds.txt: unknown type %r for %s; defaulting to rss", ftype, url)
                    ftype = "rss"
                if len(tparts) > 1:
                    selectors = _parse_selector_kwargs(tparts[1])

            feeds.append({
                "name": name,
                "url": url,
                "type": ftype,
                "selectors": selectors,
            })

    return feeds

def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()

def section(md: str, heading: str) -> str:
    m = re.search(rf"(?im)^\s*#{1,6}\s+{re.escape(heading)}\s*$", md)
    if not m:
        return ""
    rest = md[m.end():]
    m2 = re.search(r"(?im)^\s*#{1,6}\s+\S", rest)
    return (rest[:m2.start()] if m2 else rest).strip()

def parse_interests_md(md: str) -> dict:
    keywords = []
    for line in section(md, "Keywords").splitlines():
        line = re.sub(r"^[\-\*\+]\s+", "", line.strip())
        if line:
            keywords.append(line)
    narrative = section(md, "Narrative").strip()
    if len(narrative) > INTERESTS_MAX_CHARS:
        narrative = narrative[:INTERESTS_MAX_CHARS] + "…"
    return {"keywords": keywords[:200], "narrative": narrative}


# ---- rss ----
def parse_date(entry) -> datetime | None:
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

def fetch_rss_items(feeds: list[dict]) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    items = []
    for feed in feeds:
        url = feed["url"]
        d = feedparser.parse(url)

        # Priority: manual name > RSS title > URL
        source = (
            feed.get("name")
            or d.feed.get("title")
            or url
        ).strip()
        for e in d.entries[:MAX_ITEMS_PER_FEED]:
            title = (e.get("title") or "").strip()
            link = (e.get("link") or "").strip()
            if not (title and link):
                continue
            dt = parse_date(e)
            if dt and dt < cutoff:
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
    # dedupe + newest first
    items = list({it["id"]: it for it in items}.values())
    items.sort(key=lambda x: x["published_utc"] or "", reverse=True)
    return items[:MAX_TOTAL_ITEMS]



# ---- html adapter ----
_HTML_DEFAULT_ITEM_SELECTORS = (
    "article",
    "li.post", "li.news-item", "li.update",
    "div.post", "div.news-item", "div.news-card", "div.update-card",
    "[class*=NewsCard]", "[class*=PostCard]", "[class*=ArticleCard]",
)
_HTML_DEFAULT_TITLE = "h1, h2, h3, h4, .title, .headline"
_HTML_DEFAULT_LINK = "a@href"
_HTML_DEFAULT_DATE = "time@datetime, time, .date, .published"
_HTML_DEFAULT_SUMMARY = "p, .summary, .excerpt, .description"


def _split_attr(sel: str) -> tuple[str, str | None]:
    """Split `css@attr` into (css, attr). attr is None when not present."""
    if not sel:
        return sel, None
    if "@" in sel:
        css, attr = sel.rsplit("@", 1)
        return css.strip(), attr.strip() or None
    return sel.strip(), None


def _node_text(node, sel: str | None) -> str:
    """Pick best matching descendant for `sel` (which may include @attr) and return text/attr."""
    if not node:
        return ""
    if not sel:
        return (node.text(strip=True) or "").strip()
    # support multiple comma-separated selectors; pick first hit
    for one in [s.strip() for s in sel.split(",") if s.strip()]:
        css, attr = _split_attr(one)
        try:
            hit = node.css_first(css)
        except Exception:
            hit = None
        if not hit:
            continue
        if attr:
            v = hit.attributes.get(attr) or ""
        else:
            v = hit.text(strip=True) or ""
        v = (v or "").strip()
        if v:
            return v
    return ""


def _detect_rss_alternate(tree, base_url: str) -> str | None:
    try:
        link = tree.css_first('link[rel="alternate"][type*="rss"], link[rel="alternate"][type*="atom"]')
    except Exception:
        return None
    if not link:
        return None
    href = link.attributes.get("href")
    if not href:
        return None
    return urljoin(base_url, href)


def fetch_html_items(feeds: list[dict]) -> list[dict]:
    """
    Fetch items from HTML company pages using CSS selectors.

    Each feed dict is shaped like load_feeds() returns. Only feeds with
    type == "html" are processed.

    Behavior:
      - browser User-Agent; HTML_TIMEOUT seconds
      - if a `<link rel="alternate" type="application/rss+xml">` is found,
        warn loudly (caller should switch to RSS)
      - selectors fall back to a sensible default set when not provided
      - LOOKBACK_DAYS cutoff is honored only when a date can be parsed
      - returns the same item shape as fetch_rss_items()
    """
    try:
        import httpx
        from selectolax.parser import HTMLParser
    except ImportError as e:
        log.error("HTML adapter requires httpx and selectolax (%s)", e)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    items: list[dict] = []

    headers = {"User-Agent": HTML_USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    with httpx.Client(timeout=HTML_TIMEOUT, headers=headers, follow_redirects=True) as client:
        for feed in feeds:
            if feed.get("type") != "html":
                continue
            url = feed["url"]
            source = (feed.get("name") or url).strip()
            sel = feed.get("selectors") or {}
            item_sel = sel.get("item")
            title_sel = sel.get("title", _HTML_DEFAULT_TITLE)
            link_sel = sel.get("link", _HTML_DEFAULT_LINK)
            date_sel = sel.get("date", _HTML_DEFAULT_DATE)
            summary_sel = sel.get("summary", _HTML_DEFAULT_SUMMARY)

            try:
                resp = client.get(url)
            except httpx.HTTPError as e:
                log.error("HTML fetch failed for %s (%s): %s", source, url, e)
                continue
            if resp.status_code >= 400:
                log.error("HTML fetch %s -> HTTP %d for %s", source, resp.status_code, url)
                continue

            tree = HTMLParser(resp.text)

            alt = _detect_rss_alternate(tree, url)
            if alt:
                log.warning("HTML feed %s exposes RSS at %s — consider switching type=rss", source, alt)

            # find item nodes
            nodes = []
            if item_sel:
                try:
                    nodes = tree.css(item_sel)
                except Exception as e:
                    log.warning("HTML feed %s bad item selector %r: %s", source, item_sel, e)
                    nodes = []
            else:
                for css in _HTML_DEFAULT_ITEM_SELECTORS:
                    try:
                        nodes = tree.css(css)
                    except Exception:
                        nodes = []
                    if nodes:
                        log.info("HTML feed %s auto-picked item selector %r (%d nodes)", source, css, len(nodes))
                        break

            if not nodes:
                log.warning("HTML feed %s yielded 0 item nodes", source)
                continue

            kept = 0
            for node in nodes[:MAX_ITEMS_PER_FEED]:
                title = _node_text(node, title_sel)
                link_raw = _node_text(node, link_sel)
                if not (title and link_raw):
                    continue
                link = urljoin(url, link_raw)

                dt = None
                date_raw = _node_text(node, date_sel)
                if date_raw:
                    try:
                        dt = dtparser.parse(date_raw)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                    except (ValueError, TypeError):
                        dt = None
                if dt and dt < cutoff:
                    continue

                summary = _node_text(node, summary_sel)
                summary = re.sub(r"\s+", " ", summary).strip()
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
                kept += 1

            log.info("HTML feed %s -> %d items kept (from %d nodes)", source, kept, len(nodes))

    items = list({it["id"]: it for it in items}.values())
    items.sort(key=lambda x: x["published_utc"] or "", reverse=True)
    return items[:MAX_TOTAL_ITEMS]


# ---- local prefilter ----
def keyword_prefilter(items: list[dict], keywords: list[str], keep_top: int) -> list[dict]:
    kws = [k.lower() for k in keywords if k.strip()]
    def hits(it):
        text = (it.get("title","") + " " + it.get("summary","")).lower()
        return sum(1 for k in kws if k in text)
    scored = [(hits(it), it) for it in items]
    matched = [it for s, it in scored if s > 0]
    if len(matched) < min(50, keep_top):
        return items[:keep_top]
    matched.sort(key=hits, reverse=True)
    return matched[:keep_top]


# ---- triage (backend-agnostic batch loop) ----
def triage_in_batches(interests: dict, items: list[dict], batch_size: int, triage_fn) -> dict:
    """triage_fn(interests, batch) -> dict with keys notes, ranked (and optionally week_of)."""
    week_of = datetime.now(timezone.utc).date().isoformat()
    total = math.ceil(len(items) / batch_size)
    all_ranked, notes_parts = [], []

    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        print(f"Triage batch {i // batch_size + 1}/{total} ({len(batch)} items)")
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
    week_of = result["week_of"]
    notes = result.get("notes", "").strip()
    ranked = result.get("ranked", [])
    kept = [r for r in ranked if r["score"] >= MIN_SCORE_READ][:MAX_RETURNED]

    lines = [f"# Weekly ToC Digest (week of {week_of})", ""]
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
    return "\n".join(lines)


def main():
    interests = parse_interests_md(read_text("interests.md"))
    feeds = load_feeds("feeds.txt")
    rss_feeds = [f for f in feeds if f.get("type", "rss") == "rss"]
    html_feeds = [f for f in feeds if f.get("type") == "html"]

    items = fetch_rss_items(rss_feeds)
    print(f"Fetched {len(items)} RSS items (pre-filter)")

    if ENABLE_HTML and html_feeds:
        html_items = fetch_html_items(html_feeds)
        print(f"Fetched {len(html_items)} HTML items from {len(html_feeds)} feeds")
        items = items + html_items
        # re-dedupe + re-sort after merging
        items = list({it["id"]: it for it in items}.values())
        items.sort(key=lambda x: x["published_utc"] or "", reverse=True)
        items = items[:MAX_TOTAL_ITEMS]
    elif html_feeds and not ENABLE_HTML:
        log.info("HTML adapter disabled (TOCIFY_ENABLE_HTML=0); skipping %d html feeds", len(html_feeds))

    today = datetime.now(timezone.utc).date().isoformat()
    if not items:
        with open("digest.md", "w", encoding="utf-8") as f:
            f.write(f"# Weekly ToC Digest (week of {today})\n\n_No RSS items found in the last {LOOKBACK_DAYS} days._\n")
        print("No items; wrote digest.md")
        return

    items = keyword_prefilter(items, interests["keywords"], keep_top=PREFILTER_KEEP_TOP)
    print(f"Sending {len(items)} RSS items to model (post-filter)")

    items_by_id = {it["id"]: it for it in items}

    from integrations import get_triage_backend
    triage_fn = get_triage_backend()
    result = triage_in_batches(interests, items, BATCH_SIZE, triage_fn)
    md = render_digest_md(result, items_by_id)

    with open("digest.md", "w", encoding="utf-8") as f:
        f.write(md)
    print("Wrote digest.md")


if __name__ == "__main__":
    main()
