You are helping an expert analyst prepare a monthly memo for their newsletter.

**Use the Minto Pyramid Principle: lead with the main conclusions and theme, then organize supporting information hierarchically.**

We will save the memo to: `{output_path}`. Return **only** the markdown body in your response (stdout). Do not create or write to any file; we will add frontmatter and write the file ourselves.
Your response must be the **final memo article**—ready to publish. Do not output a plan, outline, or description of what you will write.
Do not use meta-language (e.g. "I will…", "This section will…"). Write the memo itself: concrete conclusions and storylines drawn only from the weekly briefs.
Use Markdown link syntax `[title](url)` for hyperlinks. Do not use HTML anchor tags like `<a href="...">...</a>`.

Generate a monthly memo from the following weekly briefs. Use only these briefs as your source.

Date range: {start_date} to {end_date}
Month: {month_name}

Weekly briefs:
{brief_refs}

Format the memo as follows:

1. Title: "## {topic_upper} Monthly Memo — {month_name}"
2. **Bottom line:** One sentence summarizing the month's main conclusion.
3. **Theme:** One sentence capturing the overarching theme or shift.
4. "### Industry Highlights" — Bullet items with [links](url) where relevant. Real content from the briefs, not placeholders.
5. "### Research Signals" — Bullet items with links. Real findings and papers from the briefs.
6. "### Clinical & Regulatory" — Bullet items (trials, clearances, policy). Real content.
7. "### Market & Ecosystem" — Bullet items (funding, deals, market data). Real content.
8. "### Emerging Narratives" — Bullet items (commentary, trends, narratives). Real content.
9. "### Further reading" — Citation list (optional extra papers/links) as bullets or short lines.
10. "### Suggested titles" — 3–5 concrete newsletter title options (real phrases, not descriptions).

Keep content comprehensive but polished. Use only information from the attached briefs.
