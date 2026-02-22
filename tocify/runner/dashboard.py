"""Build articles dashboard from briefs_articles.csv: Markdown page + JSON for Plotly graph."""

import csv
import json
from collections import Counter
from pathlib import Path

# Same columns as weekly.BRIEFS_ARTICLES_COLUMNS; defined here to avoid importing weekly (newspaper/lxml).
BRIEFS_ARTICLES_COLUMNS = [
    "topic", "week_of", "url", "title", "source", "published_utc", "score", "brief_filename",
    "why", "tags",
]


def load_articles_csv(csv_path: Path) -> list[dict]:
    """Load all rows from briefs_articles.csv into a list of dicts (same columns)."""
    if not csv_path.exists():
        return []
    rows: list[dict] = []
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        if "url" not in fieldnames:
            return rows
        for row in reader:
            rows.append({k: (row.get(k) or "").strip() for k in BRIEFS_ARTICLES_COLUMNS})
    return rows


def build_graph_payload(rows: list[dict]) -> dict:
    """Build nodes (articles + topics), edges (article -> topic), and layout for Plotly.
    Returns a dict with keys: nodes, edges, summary (byTopic, byWeek, total).
    """
    try:
        import networkx as nx
    except ImportError:
        # No layout: emit nodes with placeholder x,y; frontend can use a simple grid
        return _build_graph_payload_no_layout(rows)

    node_list: list[dict] = []
    edge_list: list[dict] = []
    topic_counts: Counter = Counter()
    week_counts: Counter = Counter()

    G = nx.Graph()
    article_ids: list[str] = []
    topic_ids: list[str] = []

    for i, r in enumerate(rows):
        url = (r.get("url") or "").strip()
        topic = (r.get("topic") or "").strip() or "unknown"
        week_of = (r.get("week_of") or "").strip()
        topic_counts[topic] += 1
        if week_of:
            week_counts[week_of] += 1

        nid = f"article_{i}"
        article_ids.append(nid)
        node_list.append({
            "id": nid,
            "title": (r.get("title") or "").strip()[:120],
            "url": url,
            "topic": topic,
            "week_of": week_of,
            "source": (r.get("source") or "").strip(),
            "score": (r.get("score") or "").strip(),
        })
        tid = f"topic_{topic}"
        if tid not in G:
            G.add_node(tid)
            topic_ids.append(tid)
        G.add_edge(nid, tid)
        edge_list.append({"source": nid, "target": tid})

    if G.order() == 0:
        return {
            "nodes": [],
            "edges": [],
            "summary": {"total": 0, "byTopic": {}, "byWeek": {}},
        }

    pos = nx.spring_layout(G, seed=42, k=0.8, iterations=50)
    for i, n in enumerate(node_list):
        nid = n["id"]
        if nid in pos:
            n["x"], n["y"] = float(pos[nid][0]), float(pos[nid][1])
        else:
            n["x"], n["y"] = 0.0, 0.0

    # Topic nodes (for display we only use article positions; topic positions can be used for labels)
    for nid in topic_ids:
        if nid in pos:
            node_list.append({
                "id": nid,
                "topic": nid.replace("topic_", ""),
                "x": float(pos[nid][0]),
                "y": float(pos[nid][1]),
                "isTopic": True,
            })

    return {
        "nodes": node_list,
        "edges": edge_list,
        "summary": {
            "total": len(rows),
            "byTopic": dict(topic_counts),
            "byWeek": dict(week_counts),
        },
    }


def _build_graph_payload_no_layout(rows: list[dict]) -> dict:
    """Fallback when networkx is not installed: simple grid positions."""
    node_list: list[dict] = []
    edge_list: list[dict] = []
    topic_counts: Counter = Counter()
    week_counts: Counter = Counter()
    topics_seen: set[str] = set()

    for i, r in enumerate(rows):
        topic = (r.get("topic") or "").strip() or "unknown"
        week_of = (r.get("week_of") or "").strip()
        topic_counts[topic] += 1
        if week_of:
            week_counts[week_of] += 1
        nid = f"article_{i}"
        topic_idx = sorted(set((row.get("topic") or "").strip() or "unknown" for row in rows)).index(topic)
        node_list.append({
            "id": nid,
            "title": (r.get("title") or "").strip()[:120],
            "url": (r.get("url") or "").strip(),
            "topic": topic,
            "week_of": week_of,
            "source": (r.get("source") or "").strip(),
            "score": (r.get("score") or "").strip(),
            "x": float(i % 10),
            "y": float(topic_idx * 2 + (i // 10) * 0.3),
        })
        edge_list.append({"source": nid, "target": f"topic_{topic}"})
        topics_seen.add(topic)

    for idx, topic in enumerate(sorted(topics_seen)):
        node_list.append({
            "id": f"topic_{topic}",
            "topic": topic,
            "x": 5.0,
            "y": float(idx * 2),
            "isTopic": True,
        })

    return {
        "nodes": node_list,
        "edges": edge_list,
        "summary": {
            "total": len(rows),
            "byTopic": dict(topic_counts),
            "byWeek": dict(week_counts),
        },
    }


def build_dashboard(
    csv_path: Path,
    output_md_path: Path,
    output_json_path: Path,
    *,
    recent_n: int = 50,
) -> None:
    """Load CSV, build graph payload, write JSON and Markdown dashboard."""
    rows = load_articles_csv(csv_path)
    payload = build_graph_payload(rows)
    summary = payload.get("summary", {})
    total = summary.get("total", 0)

    # Write JSON (for Plotly component)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    # Markdown: frontmatter + intro + optional table of recent N
    md_lines = [
        "---",
        "title: Articles Dashboard",
        "description: Interactive graph and summary of chosen articles from briefs.",
        "---",
        "",
        "Articles from the weekly briefs, by topic and week. The graph below is built from `briefs_articles.csv`.",
        "",
        f"**Total articles:** {total}",
        "",
    ]

    by_topic = summary.get("byTopic", {})
    if by_topic:
        md_lines.append("**By topic:**")
        for t, c in sorted(by_topic.items(), key=lambda x: -x[1]):
            md_lines.append(f"- {t}: {c}")
        md_lines.append("")

    # Recent N as table
    recent = rows[-recent_n:] if len(rows) > recent_n else rows
    if recent:
        md_lines.append("## Recent articles")
        md_lines.append("")
        md_lines.append("| Topic | Week | Title | Source |")
        md_lines.append("|-------|------|-------|--------|")
        for r in reversed(recent):
            title = (r.get("title") or "")[:80].replace("|", "\\|")
            url = (r.get("url") or "").strip()
            title_cell = f"[{title}]({url})" if url else title
            md_lines.append(
                f"| {r.get('topic', '')} | {r.get('week_of', '')} | {title_cell} | {r.get('source', '')} |"
            )
        md_lines.append("")

    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    output_md_path.write_text("\n".join(md_lines), encoding="utf-8")
