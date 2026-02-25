# Reference sources

## Company list (neurotech startups)

The **company list** used for prefilter and triage (see [README](../README.md#company-list)) is maintained with [Neurofounders](https://neurofounders.co) as the reference.

- **Startup Map:** <https://neurofounders.co/resources/start-up-map>  
  Interactive database of neurotech startups worldwide (BCI, neuromodulation, neuroimaging, cognitive health, etc.). Updated monthly. Use it to keep your `## Companies` section in `config/interests.<topic>.md` in sync.

- **Inclusion criteria:** <https://neurofounders.co/resources/startup-map-inclusion-criteria>  
  Explains which startups are included on the map.

Sync can be manual (copy company names into your interests file) or script-assisted; if scraping, respect [Neurofounders Terms of Use](https://neurofounders.co/terms-of-use) and rate-limit requests.

If you use a custom triage prompt (`config/triage_prompt.txt`), add a line such as `TRACKED COMPANIES: {{COMPANIES}}` so the model is given the company list; the pipeline injects `{{COMPANIES}}` from your `## Companies` section.

## Company topic pages (your data asset)

Use **`content/topics/`** to build your own company dataset:

- **One topic file per company:** e.g. `content/topics/blackrock-neurotech.md` with frontmatter `title`, `sources`, `tags`, `links_to` and a body of fact bullets.
- **Sources:** Include the Neurofounders profile URL (`https://neurofounders.co/startups/<slug>`) and later add news/article URLs as the weekly pipeline attaches them via redundant mentions.
- **Tags:** Align with Neurofounders categories (e.g. `bci`, `implantable`, `neuromodulation`) plus your own (e.g. `company`, `neurotech`).
- **Slug convention:** Prefer neurofounders-style slugs (e.g. `encora-therapeutics`) so URLs are easy to cross-reference.

The topic gardener can propose new topic pages when the weekly brief mentions a tracked company; redundant mentions will add new article URLs to existing company topic pages over time.
