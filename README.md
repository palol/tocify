# tocify — Weekly Journal ToC Digest (RSS → triage → `digest.md`)

This repo runs GitHub Actions on-demand (manual dispatch by default) that:

1. pulls new items from a list of journal RSS feeds  
2. triages items against your research interests (OpenAI API, Gemini API, or Cursor CLI)  
3. writes a ranked digest to `digest.md` and commits it back to the repo

It’s meant to be forked and customized.

---

## What’s in this repo

- **`digest.py`** — pipeline (fetch RSS → filter → triage → render markdown)
- **`tocify/integrations/`** — triage backends (OpenAI, Gemini, Cursor)
- **`feeds.txt`** — RSS feed list (comments; optional `Name | URL`)
- **`interests.md`** — keywords + narrative (used for relevance)
- **`prompt.md`** — prompt template (used by OpenAI, Gemini, and Cursor backends)
- **`digest.md`** — generated output (auto-updated)
- **`.github/workflows/weekly-digest.yml`** — manual GitHub Action (with commented weekly schedule examples)
- **`requirements.txt`** — Python dependencies
- **`.python-version`** — pinned Python version (used by uv, pyenv, etc.)

---

## Environment

Python version is pinned in **`.python-version`** (e.g. `3.11`). The repo supports **[uv](https://docs.astral.sh/uv/)** for fast, reproducible installs:

```bash
# Install uv (https://docs.astral.sh/uv/getting-started/installation/), then:
uv venv
uv pip install -r requirements.txt
uv run python digest.py
```

Alternatively use pip and a venv as usual; the GitHub workflow uses uv and reads `.python-version`.

---

## Testing

Tests use Python’s **unittest** and are run with **uv** from the project root:

```bash
uv sync
uv run python -m unittest discover -s tests -p "test_*.py" -v
```

Or use the convenience script:

```bash
uv run tocify-test
```

To run a single test module:

```bash
uv run python -m unittest tests.test_weekly_link_resolution -v
```

---

## Quick start (layperson: OpenAI)

1. **Fork** the repo.
2. Set **`OPENAI_API_KEY`** (get one from platform.openai.com). Never commit it.
3. Locally: copy `.env.example` to `.env`, add your key, run `python digest.py`.
4. For GitHub Actions: add secret **`OPENAI_API_KEY`** in Settings → Secrets. The workflow will use it; no CLI needed.

## Quick start (Cursor CLI)

1. **Fork** the repo.
2. Install the Cursor CLI and set **`CURSOR_API_KEY`** (Cursor settings).
3. For GitHub Actions: add secret **`CURSOR_API_KEY`** and keep the workflow’s Cursor install step.

## Quick start (Gemini)

1. **Fork** the repo.
2. Set **`GEMINI_API_KEY`** and optionally **`GEMINI_MODEL`** (default: `gemini-2.0-flash`).
3. Force backend with **`TOCIFY_BACKEND=gemini`**.
4. Locally: copy `.env.example` to `.env`, add your key, run `python digest.py`.

Backend selection: if **`TOCIFY_BACKEND`** is set, that backend is used. Otherwise, if **`CURSOR_API_KEY`** is set then **`cursor`** is used, else **`openai`**. Use **`TOCIFY_BACKEND=openai`**, **`cursor`**, or **`gemini`** to force. (Gemini is only used when explicitly set.)
For Cursor backend, the terminal command must be available as **`agent`** on `PATH`. The prompt is passed via stdin to avoid argument-length limits on some platforms.

---

## Configure your feeds
Edit **`feeds.txt`**.

You can use comments:

```txt
# Core journals
Nature Neuroscience | https://www.nature.com/neuro.rss
PLOS Biology | https://journals.plos.org/plosbiology/rss

# Preprints
bioRxiv neuroscience | https://www.biorxiv.org/rss/subject/neuroscience.xml
```

---

## Generated Markdown frontmatter (Quartz-friendly)

Newly generated Markdown files include YAML frontmatter with Quartz-compatible keys and tocify metadata.

Core keys:
- `date`
- `lastmod`
- `tags` (AI-suggested, normalized)
- `title` (used by `digest.md`, monthly/annual outputs, and topic pages; runner weekly briefs omit it)

Additional metadata:
- `generator`, `period`, `topic`
- period keys like `week_of`, `month`, `year`
- triage provenance: `triage_backend`, `triage_model` (and `triage_backends` / `triage_models` when mixed) — **omitted in editorial weekly briefs** (see below)
- per-file stats where applicable (`included`, `scored`, etc.)

This applies to newly generated outputs (`digest.md`, weekly briefs, monthly roundups, annual reviews, topic gardener pages). Existing files are not backfilled automatically, and runner weekly briefs intentionally do not add a `title` key.

**Weekly briefs: editorial vs legacy.** By default, weekly briefs use **editorial** output: the triage block is a single reader-facing sentence (e.g. “This week we selected N items from a larger pool of M candidates.”), frontmatter does not include `triage_backend` or `triage_model`, entry blocks do not show a score line, and internal triage phrasing (e.g. “Tier-2”, “Down-weighted”) is stripped from the “why” text. Use **`--no-editorial-triage`** to get legacy output (raw “**Included:**” / “**Scored:**” block, triage keys in frontmatter, score per entry, raw “why”).

---

## Vault / multi-topic runner (`tocify-runner`)

For multiple topics and a shared vault layout, use the **`tocify-runner`** CLI (same package). After installing the package, the command is **`tocify`** (e.g. `tocify weekly --topic bci`); help text shows the program name as "tocify-runner". It uses tocify for RSS fetch, prefilter, triage, and render; adds per-topic feeds/interests, topic redundancy vs a digital garden, topic gardener, and `briefs_articles.csv`.
Runner AI steps (weekly triage, topic redundancy, topic gardener, monthly, annual) follow the selected backend.

Set **`BCI_VAULT_ROOT`** to the vault root (directory containing `config/`, `content/`). Default is current directory.
Topic gardener is **enabled by default** for runner weekly jobs; set **`TOPIC_GARDENER=0`** to opt out.
Gardener writes topic updates as **fact bullet lists** under a persistent `## Gardner updates` section. Each new bullet gets one source footnote, and redundant articles do not trigger topic-page citation updates.
If backend is `cursor` and `agent` is not found, runner exits with an actionable error; set `TOCIFY_BACKEND=openai` or `gemini` to use API backends instead.
Weekly brief generation canonicalizes `## [Title](url)` heading links using per-brief metadata rows (exact title first, then unique normalized-title match). If no deterministic canonical match is available, the existing rendered link is kept.
Runner link hygiene now enforces Markdown hyperlink format across weekly/monthly/annual automation: trusted HTML anchors are converted to `[title](url)`, and untrusted links are de-linked.

Google News destination resolution is enabled by default for digest and weekly flows. Any item link on `news.google.com` is resolved to the destination publisher URL when possible before dedupe/filtering and output rendering. If resolution fails, tocify keeps the original Google News URL.

Google News link-resolution env toggles:
- `GOOGLE_NEWS_RESOLVE_LINKS=1` (default on; set `0` to disable)
- `GOOGLE_NEWS_RESOLVE_TIMEOUT=10` (seconds per request)
- `GOOGLE_NEWS_RESOLVE_MAX_REDIRECTS=10`
- `GOOGLE_NEWS_RESOLVE_WORKERS=8` (parallel resolution workers)

**Commands** (use **`tocify`** when running the installed package)

- **Weekly brief**: `tocify weekly --topic bci` or `tocify weekly --topic lookdeep "2025 week 2"` (use `--no-editorial-triage` for legacy raw-stats output)
- **Monthly roundup**: `tocify monthly --topic bci --month 2025-01`
- **Annual review**: `tocify annual-review --year 2025 --topic bci`
- **List topics**: `tocify list-topics`
- **Clear topic data**: `tocify clear-topic bci --yes`
- **Process whole year**: `tocify process-whole-year 2025 --topic bci`
- **Calculate weeks**: `tocify calculate-weeks 2026-01`
- **Initialize Quartz scaffold**: `tocify init-quartz --target . --write-local-exclude`
- **Changelog**: `tocify --vault . changelog` (or `tocify changelog` from vault root) — regenerate `content/changelog.md` from git (requires **git-cliff**, e.g. `brew install git-cliff`). Pipeline: git-cliff → dedupe → add dates → filter; optional polish using the same backend as triage (**`TOCIFY_BACKEND`**: openai, gemini, or cursor). Use `--mode full` for the legacy whole-file rewrite, `--mode migrate --release-label deploy-2026-03-06-init` for the one-off per-tag migration, or `--mode deploy-section --release-label deploy-2026-03-20 --from-ref deploy-2026-03-06-init --to-ref HEAD` to add one tagged deploy section. New deploy sections prepend by default; add `--append` to place them after older sections. `--no-cliff` only applies to legacy full mode, and `--no-polish` skips the polish step in any mode. Put **`cliff.toml`** at vault root and optionally **`config/changelog_consistency_prompt.md`** to override the polish prompt. Global **`--vault`** must appear before the subcommand.

`init-quartz` merges Quartz v4 scaffold paths into the target root (including `quartz/` and `content/`) and skips existing files by default. Use `--overwrite` to replace existing files. `--write-local-exclude` writes Quartz ignore rules into `.git/info/exclude` (local-only, not committed).

**Vault layout**

- `config/feeds.<topic>.txt` — RSS feeds (Name | URL)
- `config/interests.<topic>.md` — Keywords + Narrative (+ optional **Companies**; see [Company list](docs/sources.md#company-list-neurotech-startups))
- `config/triage_prompt.md` — Shared triage prompt
- `config/gardener_prompt.md` — Topic gardener prompt (optional; defaults to bundled template)
- `config/monthly_roundup_prompt.md` — Monthly roundup prompt (optional)
- `config/annual_review_prompt.md` — Annual review prompt (optional)
- `content/briefs_articles.csv` — Chosen articles (topic column)
- `content/feeds/weekly/` — Weekly briefs (`YYYY week N.md`)
- `content/feeds/monthly/` — Monthly roundups (`YYYY-MM.md`)
- `content/feeds/yearly/` — Annual reviews (`YYYY review.md`)
- `logs/` — Logs (at vault root; e.g. topic_actions_*.json, roundup logs)
- `content/topics/` — Optional digital garden for topic redundancy and gardener

**Industry backends** (weekly run)

Beyond RSS and OpenAlex/NewsAPI/Google News, the weekly runner can pull from neurotech/industry sources. Each backend returns the same item schema and is merged with RSS before triage. Enable via env and optional per-topic config:

| Env / config | Purpose |
|--------------|--------|
| `ADD_CLINICAL_TRIALS=1` | Enable ClinicalTrials.gov (studies by date range; optional search via `CLINICALTRIALS_QUERY` or topic keywords) |
| `ADD_EDGAR=1` | Enable SEC EDGAR company filings (by CIK). Set `EDGAR_CIKS` (comma-separated) or use `config/edgar_ciks.<topic>.txt` (one CIK per line) |
| `ADD_NEWSROOMS=1` | Enable company newsroom scraper (experimental). Set `NEWSROOMS_URLS` (newline-separated) or use `config/newsrooms.<topic>.txt` (one index URL per line). Only links with a date in the URL path are included. |

**Automation notes**

- This repository keeps workflows manual (`workflow_dispatch`) so no weekly jobs trigger automatically here.
- Each workflow includes commented `schedule` examples that forks can enable for weekly automation.
- `.github/workflows/weekly-runner.yml` runs `tocify.runner` when dispatched and runner config files exist. It supports **OpenAI** (secret `OPENAI_API_KEY`) or **Cursor CLI** (secret `CURSOR_API_KEY`); if both are set, OpenAI is used. For Cursor, the workflow installs the Cursor CLI in the runner environment.
- Legacy digest workflows (`weekly-digest.yml`, `weekly-digest-cursor.yml`) run `digest.py` only; they do not invoke runner gardener.
