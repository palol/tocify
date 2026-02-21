"""Weekly digest for one topic: fetch (tocify), prefilter, triage, topic redundancy, gardener, brief + CSV."""

import csv
import json
import math
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import date, datetime, time as dt_time, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from dotenv import load_dotenv
from newspaper import Article
from tqdm import tqdm

import tocify
from tocify.runner.vault import get_topic_paths, VAULT_ROOT

load_dotenv()

# Env (same names as neural-noise / tocify)
MAX_ITEMS_PER_FEED = int(os.getenv("MAX_ITEMS_PER_FEED", "50"))
MAX_TOTAL_ITEMS = int(os.getenv("MAX_TOTAL_ITEMS", "400"))
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "7"))
SUMMARY_MAX_CHARS = int(os.getenv("SUMMARY_MAX_CHARS", "500"))
PREFILTER_KEEP_TOP = int(os.getenv("PREFILTER_KEEP_TOP", "200"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "50"))
MIN_SCORE_READ = float(os.getenv("MIN_SCORE_READ", "0.65"))
MAX_RETURNED = int(os.getenv("MAX_RETURNED", "40"))
USE_NEWSPAPER = os.getenv("USE_NEWSPAPER", "0").strip().lower() in ("1", "true", "yes")
NEWSPAPER_MAX_ITEMS = int(os.getenv("NEWSPAPER_MAX_ITEMS", "100"))
NEWSPAPER_TIMEOUT = int(os.getenv("NEWSPAPER_TIMEOUT", "10"))
TOPIC_REDUNDANCY_ENABLED = os.getenv("TOPIC_REDUNDANCY", "1").strip().lower() in ("1", "true", "yes")
TOPIC_REDUNDANCY_LOOKBACK_DAYS = int(os.getenv("TOPIC_REDUNDANCY_LOOKBACK_DAYS", "56"))
TOPIC_REDUNDANCY_BATCH_SIZE = int(os.getenv("TOPIC_REDUNDANCY_BATCH_SIZE", "25"))
TOPIC_GARDENER_ENABLED = os.getenv("TOPIC_GARDENER", "1").strip().lower() in ("1", "true", "yes")

BRIEFS_ARTICLES_COLUMNS = [
    "topic", "week_of", "url", "title", "source", "published_utc", "score", "brief_filename",
    "why", "tags",
]

TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "msclkid", "ref", "mc_cid", "mc_eid", "_ga",
})


def parse_week_spec(s: str) -> str:
    """Parse 'YYYY week N' (ISO week); return Monday of that week as YYYY-MM-DD."""
    s = (s or "").strip()
    m = re.match(r"^(\d{4})\s+week\s+(\d+)$", s, re.IGNORECASE)
    if not m:
        raise ValueError(f"Invalid week spec: expected 'YYYY week N', got {s!r}")
    year, week = int(m.group(1)), int(m.group(2))
    if week < 1 or week > 53:
        raise ValueError(f"Invalid ISO week number: {week} (must be 1-53)")
    d = date.fromisocalendar(year, week, 1)
    return d.isoformat()


def normalize_url_for_dedup(url: str) -> str:
    if not (url or url.strip()):
        return ""
    s = url.strip()
    parsed = urlparse(s)
    query = parse_qs(parsed.query, keep_blank_values=False)
    filtered = {k: v for k, v in query.items() if k.lower() not in TRACKING_PARAMS}
    new_query = urlencode(sorted(filtered.items()), doseq=True)
    no_fragment = parsed._replace(query=new_query, fragment="")
    return urlunparse(no_fragment)


def load_briefs_articles_urls(csv_path: Path, topic: str | None = None) -> set[str]:
    seen = set()
    if not csv_path.exists():
        return seen
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        if "url" not in fieldnames:
            return seen
        has_topic_col = "topic" in fieldnames
        for row in reader:
            if topic is not None and has_topic_col and (row.get("topic") or "").strip() != topic:
                continue
            u = (row.get("url") or "").strip()
            if u:
                seen.add(normalize_url_for_dedup(u))
    return seen


def load_recent_topic_files(topics_dir: Path, max_age_days: int) -> list[Path]:
    if not topics_dir.exists() or max_age_days <= 0:
        return []
    now = datetime.now(timezone.utc)
    cutoff_ts = (now - timedelta(days=max_age_days)).timestamp()
    out = []
    for p in topics_dir.glob("*.md"):
        if not p.is_file():
            continue
        try:
            if p.stat().st_mtime >= cutoff_ts:
                out.append(p)
        except OSError:
            continue
    out.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return out


def enrich_item_with_newspaper(item: dict, timeout: int) -> dict:
    link = (item.get("link") or "").strip()
    if not link:
        return item

    def download_and_parse():
        article = Article(link)
        article.download()
        article.parse()
        return article.text or ""

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(download_and_parse)
            text = fut.result(timeout=timeout)
    except (FuturesTimeoutError, Exception):
        return item

    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return item
    if len(text) > SUMMARY_MAX_CHARS:
        text = text[:SUMMARY_MAX_CHARS] + "…"
    item["summary"] = text
    return item


# ---- topic redundancy ----
TOPIC_REDUNDANCY_PROMPT = """You have reference topic documents (each summarizes a story or theme we already cover in our newsletter). Below are candidate RSS items.

For each candidate item:
1. Which topic file, if any, does this article belong to? (same story or theme)
2. If it matches a topic: does this article add **new knowledge** beyond what the topic summary and its sources already cover?

If an item matches a topic AND does **not** add new knowledge, it is redundant and should be excluded from the brief.

Reference topic documents:
{topic_refs}

Candidate RSS items:
{items_json}

Return **only** a single JSON object, no markdown code fences, no commentary. Schema:
{{"redundant_ids": ["<id1>", "<id2>", ...]}}
List the "id" of each candidate item that is redundant."""


def _call_cursor_topic_redundancy(topic_paths: list[Path], items: list[dict]) -> set[str]:
    if not topic_paths or not items:
        return set()
    topic_refs = "\n".join(f"@{p.resolve()}" for p in topic_paths)
    lean_items = [
        {
            "id": it["id"],
            "title": it.get("title", ""),
            "link": it.get("link", ""),
            "source": it.get("source", ""),
            "summary": (it.get("summary") or "")[:SUMMARY_MAX_CHARS],
        }
        for it in items
    ]
    prompt = TOPIC_REDUNDANCY_PROMPT.format(
        topic_refs=topic_refs,
        items_json=json.dumps(lean_items, ensure_ascii=False),
    )
    args = ["agent", "-p", "--output-format", "text", "--trust", prompt]
    result = subprocess.run(args, capture_output=True, text=True, env=os.environ)
    if result.returncode != 0:
        raise RuntimeError(
            f"cursor topic-redundancy exit {result.returncode}: {result.stderr or result.stdout or 'no output'}"
        )
    response_text = (result.stdout or "").strip()
    start = response_text.find("{")
    end = response_text.rfind("}") + 1
    if start < 0 or end <= start:
        return set()
    try:
        parsed = json.loads(response_text[start:end])
    except json.JSONDecodeError:
        return set()
    redundant = parsed.get("redundant_ids")
    if not isinstance(redundant, list):
        return set()
    return {str(x) for x in redundant if x}


def filter_topic_redundant_items(
    topic_paths: list[Path],
    items: list[dict],
    batch_size: int,
    redundancy_log_path: Path | None = None,
) -> tuple[list[dict], int]:
    if not topic_paths or not items:
        return items, 0
    all_redundant: set[str] = set()
    batch_starts = list(range(0, len(items), batch_size))
    disable = not sys.stderr.isatty()
    for i in tqdm(batch_starts, desc="Topic redundancy", unit="batch", disable=disable):
        batch = items[i : i + batch_size]
        redundant = _call_cursor_topic_redundancy(topic_paths, batch)
        all_redundant |= redundant
    if redundancy_log_path is not None:
        redundancy_log_path.parent.mkdir(parents=True, exist_ok=True)
        redundancy_log_path.write_text(
            json.dumps({"redundant_ids": sorted(all_redundant)}, indent=2),
            encoding="utf-8",
        )
    kept = [it for it in items if it["id"] not in all_redundant]
    return kept, len(items) - len(kept)


# ---- topic gardener ----
TOPIC_GARDENER_PROMPT = """You are curating a **global digital garden** of evergreen topic pages.

Below are (1) this week's weekly brief, and (2) existing topic files. Propose **create** or **update** actions.

Rules:
- **create**: New topic when the brief introduces a distinct theme. Use lowercase-hyphen slug. Include title, body_markdown, sources, links_to.
- **update**: When an item adds to an existing topic. Provide slug, append_sources, optionally summary_addendum.

This week's brief (category: {topic}):
{brief_content}

Existing topic files (slug and preview):
{existing_topics}

Return **only** a single JSON object. Schema:
{{"topic_actions": [{{ "action": "create" | "update", "slug": "<slug>", "title": "<title>", "body_markdown": "<markdown>", "sources": ["url"], "links_to": ["slug"], "append_sources": ["url"], "summary_addendum": "<markdown>" }}]}}
Omit topic_actions or use [] if nothing to do."""


def _list_existing_topic_previews(topics_dir: Path, max_preview_chars: int = 400) -> list[dict]:
    if not topics_dir.exists():
        return []
    out = []
    for p in sorted(topics_dir.glob("*.md")):
        if not p.is_file():
            continue
        slug = p.stem
        try:
            text = p.read_text(encoding="utf-8")
            preview = text.strip()[:max_preview_chars]
            if len(text.strip()) > max_preview_chars:
                preview += "…"
        except Exception:
            preview = ""
        out.append({"slug": slug, "preview": preview})
    return out


def _call_cursor_topic_gardener(brief_content: str, existing_topics: list[dict], topic: str) -> list[dict]:
    existing_str = "\n\n".join(
        f"- **{t['slug']}**:\n{t['preview']}" for t in existing_topics
    ) or "(no existing topics yet)"
    prompt = TOPIC_GARDENER_PROMPT.format(
        topic=topic,
        brief_content=brief_content,
        existing_topics=existing_str,
    )
    args = ["agent", "-p", "--output-format", "text", "--trust", prompt]
    result = subprocess.run(args, capture_output=True, text=True, env=os.environ)
    if result.returncode != 0:
        raise RuntimeError(
            f"cursor topic-gardener exit {result.returncode}: {result.stderr or result.stdout or 'no output'}"
        )
    response_text = (result.stdout or "").strip()
    start = response_text.find("{")
    end = response_text.rfind("}") + 1
    if start < 0 or end <= start:
        return []
    try:
        parsed = json.loads(response_text[start:end])
    except json.JSONDecodeError:
        return []
    actions = parsed.get("topic_actions")
    if not isinstance(actions, list):
        return []
    return actions


def _apply_topic_action(topics_dir: Path, action: dict, today: str) -> None:
    act = (action.get("action") or "").strip().lower()
    slug = (action.get("slug") or "").strip()
    if not slug or act not in ("create", "update"):
        return
    slug = re.sub(r"[^a-z0-9\-]", "", slug.lower().replace("_", "-")) or "untitled"
    path = topics_dir / f"{slug}.md"

    if act == "create":
        title = (action.get("title") or slug).strip()
        body_markdown = (action.get("body_markdown") or "").strip()
        sources = action.get("sources") if isinstance(action.get("sources"), list) else []
        sources = [str(s).strip() for s in sources if str(s).strip()]
        links_to = action.get("links_to") if isinstance(action.get("links_to"), list) else []
        links_to = [str(s).strip() for s in links_to if str(s).strip()]
        frontmatter_lines = ["---", f'title: "{title}"', f'updated: "{today}"']
        if sources:
            frontmatter_lines.append("sources:")
            for u in sources:
                frontmatter_lines.append(f'  - "{u}"')
        if links_to:
            frontmatter_lines.append("links_to:")
            for s in links_to:
                frontmatter_lines.append(f'  - "{s}"')
        frontmatter_lines.append("---")
        path.write_text("\n".join(frontmatter_lines) + "\n\n" + body_markdown, encoding="utf-8")
        return

    if act == "update" and path.exists():
        append_sources = action.get("append_sources")
        if isinstance(append_sources, list):
            append_sources = [str(s).strip() for s in append_sources if str(s).strip()]
        else:
            append_sources = []
        summary_addendum = (action.get("summary_addendum") or "").strip()
        to_append = []
        if summary_addendum:
            to_append.append(f"\n\n## Recent update ({today})\n\n{summary_addendum}")
        if append_sources:
            to_append.append("\n\n### New sources\n\n" + "\n".join(f"- {u}" for u in append_sources))
        if to_append:
            existing = path.read_text(encoding="utf-8")
            path.write_text(existing + "".join(to_append), encoding="utf-8")


def run_topic_gardener(
    topics_dir: Path,
    brief_path: Path,
    topic: str,
    logs_dir: Path | None = None,
    week_of: str | None = None,
) -> None:
    topics_dir.mkdir(parents=True, exist_ok=True)
    if not brief_path.exists():
        return
    brief_content = brief_path.read_text(encoding="utf-8")
    existing_topics = _list_existing_topic_previews(topics_dir)
    disable = not sys.stderr.isatty()
    with tqdm(desc="Topic gardener (agent)", total=None, unit="", disable=disable):
        actions = _call_cursor_topic_gardener(brief_content, existing_topics, topic)
    if logs_dir is not None and week_of is not None:
        logs_dir.mkdir(parents=True, exist_ok=True)
        out_path = logs_dir / f"topic_actions_{week_of}_{topic}.json"
        out_path.write_text(
            json.dumps({"topic_actions": actions}, indent=2),
            encoding="utf-8",
        )
    today = datetime.now(timezone.utc).date().isoformat()
    valid_actions = [a for a in actions if isinstance(a, dict)]
    applied = 0
    for a in tqdm(valid_actions, desc="Topic gardener (apply)", unit="action", disable=disable):
        try:
            _apply_topic_action(topics_dir, a, today)
            applied += 1
        except Exception as e:
            tqdm.write(f"[WARN] Topic gardener: failed to apply action {a.get('slug', '?')}: {e}")
    if applied > 0:
        tqdm.write(f"Topic gardener: applied {applied} topic action(s) under {topics_dir}")


def render_brief_md(
    result: dict, items_by_id: dict[str, dict], kept: list[dict], topic: str
) -> str:
    week_of = result["week_of"]
    notes = result.get("notes", "").strip()
    ranked = result.get("ranked", [])

    lines = [f"# {topic.upper()} Weekly Brief (week of {week_of})", ""]
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
            (r.get("why") or "").strip(),
            "",
        ]
        if summary:
            lines += ["<details>", "<summary>RSS summary</summary>", "", summary, "", "</details>", ""]
        lines += ["---", ""]
    return "\n".join(lines)


def append_briefs_articles(
    csv_path: Path,
    topic: str,
    week_of: str,
    kept: list[dict],
    items_by_id: dict[str, dict],
    brief_filename: str,
) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=BRIEFS_ARTICLES_COLUMNS)
        if not file_exists:
            writer.writeheader()
        for r in kept:
            it = items_by_id.get(r["id"], {})
            row = {
                "topic": topic,
                "week_of": week_of,
                "url": r.get("link") or it.get("link", ""),
                "title": r.get("title") or it.get("title", ""),
                "source": r.get("source") or it.get("source", ""),
                "published_utc": r.get("published_utc") or it.get("published_utc") or "",
                "score": str(r.get("score", "")),
                "brief_filename": brief_filename,
                "why": (r.get("why") or "").strip().replace("\n", " "),
                "tags": "|".join(r.get("tags") or []),
            }
            writer.writerow(row)


def run_weekly(
    topic: str,
    week_spec: str | None = None,
    dry_run: int = 0,
    vault_root: Path | None = None,
) -> None:
    """Run weekly digest for one topic. Uses tocify for fetch/prefilter/triage/render params; runner adds vault, redundancy, gardener."""
    root = vault_root or VAULT_ROOT
    paths = get_topic_paths(topic, vault_root=root)
    if not paths.feeds_path.exists():
        raise FileNotFoundError(f"Feeds file not found: {paths.feeds_path}")
    if not paths.interests_path.exists():
        raise FileNotFoundError(f"Interests file not found: {paths.interests_path}")
    if not paths.prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {paths.prompt_path}")

    interests = tocify.parse_interests_md(paths.interests_path.read_text(encoding="utf-8"))
    feeds = tocify.load_feeds(str(paths.feeds_path))

    if week_spec is not None:
        week_of = parse_week_spec(week_spec)
        end_date = datetime.strptime(week_of, "%Y-%m-%d").date()
    else:
        today = datetime.now(timezone.utc).date()
        week_of = date.fromisocalendar(
            today.isocalendar()[0], today.isocalendar()[1], 1
        ).isoformat()
        end_date = None

    items = tocify.fetch_rss_items(feeds, end_date=end_date)
    tqdm.write(f"Fetched {len(items)} RSS items (pre-filter) [topic={topic}]")

    paths.briefs_dir.mkdir(parents=True, exist_ok=True)
    brief_filename = f"{week_of}_{topic}_weekly-brief.md"
    brief_path = paths.briefs_dir / brief_filename

    if not items:
        brief_path.write_text(
            f"# {topic.upper()} Weekly Brief (week of {week_of})\n\n_No RSS items found in the last {LOOKBACK_DAYS} days._\n",
            encoding="utf-8",
        )
        tqdm.write(f"No items; wrote {brief_path}")
        return

    items = tocify.keyword_prefilter(
        items, interests["keywords"], keep_top=PREFILTER_KEEP_TOP
    )
    seen_norm = {}
    deduped = []
    for it in items:
        link = (it.get("link") or "").strip()
        norm = normalize_url_for_dedup(link)
        if norm and norm not in seen_norm:
            seen_norm[norm] = True
            deduped.append(it)
    if len(deduped) < len(items):
        tqdm.write(f"Deduped by normalized URL: {len(items)} -> {len(deduped)}")
    items = deduped

    briefs_urls = load_briefs_articles_urls(paths.briefs_articles_csv, topic=topic)
    before_cross = len(items)
    items = [it for it in items if normalize_url_for_dedup((it.get("link") or "").strip()) not in briefs_urls]
    if before_cross > len(items):
        tqdm.write(f"Cross-week filter: dropped {before_cross - len(items)} items, {len(items)} remaining")

    topics_dir = root / "topics"
    if TOPIC_REDUNDANCY_ENABLED and items:
        topics_dir.mkdir(parents=True, exist_ok=True)
    if TOPIC_REDUNDANCY_ENABLED and topics_dir.exists() and items:
        topic_paths = load_recent_topic_files(topics_dir, TOPIC_REDUNDANCY_LOOKBACK_DAYS)
        if topic_paths:
            tqdm.write(f"Topic redundancy: checking {len(items)} items against {len(topic_paths)} topic file(s)")
            items, dropped = filter_topic_redundant_items(
                topic_paths,
                items,
                TOPIC_REDUNDANCY_BATCH_SIZE,
                redundancy_log_path=paths.logs_dir / "rss_redundancy_result.json",
            )
            if dropped > 0:
                tqdm.write(f"Topic redundancy: dropped {dropped} items, {len(items)} remaining")

    if dry_run:
        items = items[:dry_run]
        tqdm.write(f"Dry run: capped to {len(items)} items (no CSV append)")

    tqdm.write(f"Sending {len(items)} RSS items to model (post-filter)")

    if USE_NEWSPAPER:
        to_enrich = items[:NEWSPAPER_MAX_ITEMS]
        disable_newspaper = not sys.stderr.isatty()
        for i, it in enumerate(tqdm(to_enrich, desc="Newspaper", disable=disable_newspaper)):
            enrich_item_with_newspaper(it, NEWSPAPER_TIMEOUT)
            if i < len(to_enrich) - 1:
                time.sleep(0.2)

    items_by_id = {it["id"]: it for it in items}

    if not os.environ.get("CURSOR_API_KEY", "").strip():
        raise RuntimeError("CURSOR_API_KEY must be set.")

    os.environ["TOCIFY_PROMPT_PATH"] = str(paths.prompt_path)
    triage_fn = tocify.get_triage_backend()
    result = tocify.triage_in_batches(interests, items, BATCH_SIZE, triage_fn)
    result["week_of"] = week_of

    ranked = result.get("ranked", [])
    kept = [r for r in ranked if r["score"] >= MIN_SCORE_READ][:MAX_RETURNED]
    md = render_brief_md(result, items_by_id, kept, topic)
    brief_path.write_text(md, encoding="utf-8")
    tqdm.write(f"Wrote {brief_path}")

    if not dry_run and kept:
        append_briefs_articles(
            paths.briefs_articles_csv,
            topic,
            result["week_of"],
            kept,
            items_by_id,
            brief_filename,
        )
        tqdm.write(f"Appended {len(kept)} rows to {paths.briefs_articles_csv}")

    if TOPIC_GARDENER_ENABLED and not dry_run and kept:
        topics_dir.mkdir(parents=True, exist_ok=True)
        run_topic_gardener(
            topics_dir, brief_path, topic,
            logs_dir=paths.logs_dir, week_of=week_of,
        )
