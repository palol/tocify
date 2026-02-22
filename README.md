# tocify — Weekly Journal ToC Digest (RSS → triage → `digest.md`)

This repo runs a GitHub Action once a week (or on-demand) that:

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
- **`prompt.txt`** — prompt template (used by OpenAI, Gemini, and Cursor backends)
- **`digest.md`** — generated output (auto-updated)
- **`.github/workflows/weekly-digest.yml`** — scheduled GitHub Action
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
For Cursor backend, the terminal command must be available as **`agent`** on `PATH`.

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
- `title`
- `date`
- `lastmod`
- `tags` (AI-suggested, normalized)

Additional metadata:
- `generator`, `period`, `topic`
- period keys like `week_of`, `month`, `year`
- triage provenance: `triage_backend`, `triage_model` (and `triage_backends` / `triage_models` when mixed)
- per-file stats where applicable (`included`, `scored`, etc.)

This applies to newly generated outputs (`digest.md`, weekly briefs, monthly roundups, annual reviews, topic gardener pages). Existing files are not backfilled automatically.

---

## Vault / multi-topic runner (`tocify-runner`)

For multiple topics and a shared vault layout, use the **`tocify-runner`** CLI (same package). After installing the package, the command is **`tocify`** (e.g. `tocify weekly --topic bci`); help text shows the program name as "tocify-runner". It uses tocify for RSS fetch, prefilter, triage, and render; adds per-topic feeds/interests, topic redundancy vs a digital garden, topic gardener, and `briefs_articles.csv`.
Runner AI steps (weekly triage, topic redundancy, topic gardener, monthly, annual) follow the selected backend.

Set **`BCI_VAULT_ROOT`** to the vault root (directory containing `config/`, `content/`). Default is current directory.
Topic gardener is **enabled by default** for runner weekly jobs; set **`TOPIC_GARDENER=0`** to opt out.
Gardener writes topic updates as **fact bullet lists** under a persistent `## Gardner updates` section. Each new bullet gets one source footnote, and redundant articles do not trigger topic-page citation updates.
If backend is `cursor` and `agent` is not found, runner exits with an actionable error; set `TOCIFY_BACKEND=openai` or `gemini` to use API backends instead.
Weekly brief generation now canonicalizes `## [Title](url)` heading links using per-brief metadata rows (exact title first, then unique normalized-title match). If no deterministic canonical match is available, the existing rendered link is kept. This applies to newly generated weekly briefs; monthly and annual outputs are unchanged in this cycle.

**Commands** (use **`tocify`** when running the installed package)

- **Weekly brief**: `tocify weekly --topic bci` or `tocify weekly --topic lookdeep "2025 week 2"`
- **Monthly roundup**: `tocify monthly --topic bci --month 2025-01`
- **Annual review**: `tocify annual-review --year 2025 --topic bci`
- **List topics**: `tocify list-topics`
- **Clear topic data**: `tocify clear-topic bci --yes`
- **Process whole year**: `tocify process-whole-year 2025 --topic bci`
- **Calculate weeks**: `tocify calculate-weeks 2026-01`
- **Initialize Quartz scaffold**: `tocify init-quartz --target . --write-local-exclude`

`init-quartz` merges Quartz v4 scaffold paths into the target root (including `quartz/` and `content/`) and skips existing files by default. Use `--overwrite` to replace existing files. `--write-local-exclude` writes Quartz ignore rules into `.git/info/exclude` (local-only, not committed).

**Vault layout**

- `config/feeds.<topic>.txt` — RSS feeds (Name | URL)
- `config/interests.<topic>.md` — Keywords + Narrative
- `config/triage_prompt.txt` — Shared triage prompt
- `content/briefs_articles.csv` — Chosen articles (topic column)
- `content/briefs/` — Weekly briefs and monthly/annual outputs
- `content/logs/` — Logs
- `content/topics/` — Optional digital garden for topic redundancy and gardener

**Automation notes**

- `.github/workflows/weekly-runner.yml` runs `tocify.runner` weekly when runner config files exist. The workflow supports **OpenAI** (secret `OPENAI_API_KEY`) or **Cursor CLI** (secret `CURSOR_API_KEY`); if both are set, OpenAI is used. For Cursor, the workflow installs the Cursor CLI in the runner environment.
- Legacy digest workflows (`weekly-digest.yml`, `weekly-digest-cursor.yml`) run `digest.py` only; they do not invoke runner gardener.
