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

Backend is auto-chosen from which key is set, or set **`TOCIFY_BACKEND=openai`**, **`cursor`**, or **`gemini`** to force.

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

For multiple topics and a shared vault layout, use the **`tocify-runner`** CLI (same package). It uses tocify for RSS fetch, prefilter, triage, and render; adds per-topic feeds/interests, topic redundancy vs a digital garden, topic gardener, and `briefs_articles.csv`.

Set **`BCI_VAULT_ROOT`** to the vault root (directory containing `config/`, `agent/`). Default is current directory.

**Commands**

- **Weekly brief**: `tocify-runner weekly --topic bci` or `tocify-runner weekly --topic lookdeep "2025 week 2"`
- **Monthly roundup**: `tocify-runner monthly --topic bci --month 2025-01`
- **Annual review**: `tocify-runner annual-review --year 2025 --topic bci`
- **List topics**: `tocify-runner list-topics`
- **Clear topic data**: `tocify-runner clear-topic bci --yes`
- **Process whole year**: `tocify-runner process-whole-year 2025 --topic bci`
- **Calculate weeks**: `tocify-runner calculate-weeks 2026-01`

**Vault layout**

- `config/feeds.<topic>.txt` — RSS feeds (Name | URL)
- `config/interests.<topic>.md` — Keywords + Narrative
- `config/triage_prompt.txt` — Shared triage prompt
- `config/briefs_articles.csv` — Chosen articles (topic column)
- `agent/briefs/` — Weekly briefs and monthly/annual outputs
- `agent/logs/` — Logs
- `topics/` — Optional digital garden for topic redundancy and gardener
