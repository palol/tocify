You are helping an expert analyst prepare a monthly roundup for their newsletter.

**Use the Minto Pyramid Principle: structure the roundup to lead with the main conclusions and storylines, then organize supporting information hierarchically.**

We will save the roundup to: `{output_path}`. Return **only** the markdown body in your response (stdout). Do not create or write to any file; we will add frontmatter and write the file ourselves.
Your response must be the **final roundup article**—ready to publish. Do not output a plan, outline, or description of what you will write.
Do not use meta-language (e.g. "I will…", "This section will…"). Write the roundup itself: concrete conclusions and storylines drawn only from the weekly briefs.
Use Markdown link syntax `[title](url)` for hyperlinks. Do not use HTML anchor tags like `<a href="...">...</a>`.

Generate a monthly roundup from the following weekly briefs. Use only these briefs as your source.

Date range: {start_date} to {end_date}
Month: {month_name}

Weekly briefs:
{brief_refs}

Format the roundup as follows:
1. Title: "# {topic_upper} Monthly Roundup — {month_name}"
2. Date range subtitle
3. "## Introduction" — 1–2 full paragraphs summarizing the month's key storylines (actual summary prose, not one-line placeholders).
4. "## Suggested Titles" — 3–5 concrete newsletter title options (real phrases, not a description of what titles could be).
5. Sections by theme (Papers and Prototypes, Clinical and Regulatory, Companies and Funding, Emerging Themes). Each section: a summary statement then real items from the briefs (title, source/date, link, summary)—not bullet plans like "Include items on X and Y."

Keep content comprehensive but polished.
