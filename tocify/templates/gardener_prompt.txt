You are curating a **global digital garden** of evergreen topic pages.

Below are (1) this week's weekly brief, and (2) existing topic files. Propose **create** or **update** actions.

Return only the JSON object; we will create or update topic files from it. Do not write to any file path.

Rules:
- **create**: New topic when the brief introduces a distinct theme. Use lowercase-hyphen slug. Include title, body_markdown, sources, links_to, tags.
  - When the brief mentions a **tracked company** (see list below), prefer creating a topic page for that company if one does not exist.
  - `body_markdown` must be a **fact bullet list** (`- Fact...`), not prose paragraphs. Write the actual fact bullets drawn from the brief, not a description of what to add.
- **update**: Only when the brief adds genuinely new knowledge to an existing topic. Provide slug, append_sources, optionally summary_addendum, summary_addendum_sources, and tags.
  - `summary_addendum` must be a **fact bullet list** (`- Fact...`) when present. Write the actual fact bullets, not a description of what to add.
- Each bullet in `summary_addendum` must map to exactly one source URL in `summary_addendum_sources` (same order, same length).
- Use source attribution with markdown footnotes, e.g. [^1] and [^1]: https://example.com.
- For inline hyperlinks in markdown fields, use Markdown syntax `[title](url)`. Do not use HTML anchors like `<a href="...">...</a>`.
- If no new knowledge is present, do not emit an update action.

Tracked companies (strong candidates for new topic pages when mentioned in the brief):
{tracked_companies}

This week's brief (category: {topic}):
{brief_content}

Existing topic files (slug and preview):
{existing_topics}

Return **only** a single JSON object. Schema:
{{"topic_actions": [{{ "action": "create" | "update", "slug": "<slug>", "title": "<title>", "body_markdown": "<markdown>", "sources": ["url"], "links_to": ["slug"], "append_sources": ["url"], "summary_addendum": "<markdown>", "summary_addendum_sources": ["url"], "tags": ["tag"] }}]}}
Bullet examples for markdown fields:
- body_markdown: "- Fact one.\n- Fact two."
- summary_addendum: "- New finding one.\n- New finding two."
Omit topic_actions or use [] if nothing to do.
