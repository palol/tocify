You are helping an expert analyst prepare an annual review for their newsletter.

**Use the Minto Pyramid Principle: lead with the year's main conclusions, then organize by category and chronology.**

We will save the review to: `{output_path}`. Return **only** the markdown body in your response (stdout). Do not create or write to any file; we will add frontmatter and write the file ourselves.
Your response must be the **final annual review article**—ready to publish. Do not output a plan, outline, or description of what you will write.
Do not use meta-language (e.g. "I will…", "This section will…"). Write the review itself: concrete events, conclusions, and storylines drawn only from the monthly roundups.
Use Markdown link syntax `[title](url)` for hyperlinks. Do not use HTML anchor tags like `<a href="...">...</a>`.

Generate an annual review for the year {year}. Use only the following monthly roundups as your source. Do not invent content.

Monthly roundups (in chronological order):
{roundup_refs}

Format the review as follows:

1. "## {year} at a glance" — Opening section with bold category headers and bullet points beneath each:
   - **Clinical and commercial** — Bullet points (clearances, trials, commercial milestones).
   - **Applications and hardware** — Bullet points (speech, motor, sensory, tools).
   - **Governance and policy** — Bullet points (regulation, ethics, legislation).

2. "---" (horizontal rule)

3. "## Timeline" — Month-by-month narrative. For each month use "### MonthName" (e.g. ### January) followed by bullet points of real events from the roundups. Cover all months that have content in the roundups.

Keep content comprehensive but polished. Use only information from the attached roundups. Do not add a "Trends" or "Suggested titles" section.
