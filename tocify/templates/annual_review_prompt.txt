You are helping an expert analyst prepare an annual review for their newsletter.

**Use the Minto Pyramid Principle: structure the review to lead with the main conclusions and storylines of the year, then organize supporting information hierarchically.**

We will save the review to: `{output_path}`. Return **only** the markdown body in your response (stdout). Do not create or write to any file; we will add frontmatter and write the file ourselves.
Your response must be the **final annual review article**—ready to publish. Do not output a plan, outline, or description of what you will write.
Do not use meta-language (e.g. "I will…", "This section will…"). Write the review itself: concrete conclusions, events, and storylines drawn only from the monthly roundups.
Use Markdown link syntax `[title](url)` for hyperlinks. Do not use HTML anchor tags like `<a href="...">...</a>`.

Generate an annual review for the year {year}. Use only the following monthly roundups as your source. Do not invent content.

Monthly roundups (in chronological order):
{roundup_refs}

Format the review as follows:
1. Title: e.g. "# {topic_upper} Annual Review — {year}" and a date range subtitle
2. "## Introduction" — 2–4 full paragraphs with the year's main conclusions and storylines (no placeholders).
3. "## Timelines" — Chronological narrative or month-by-month highlights with real events from the roundups.
4. "## Trends" — Thematic arcs across the year with real content; use subheadings if helpful—not a list of "we could cover X, Y."
5. Optional: "## Suggested Titles" — 3–5 concrete newsletter title options (real phrases, not a description).

Keep content comprehensive but polished. Use only information from the attached roundups.
