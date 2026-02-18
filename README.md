# tocify — Weekly Journal ToC Digest (RSS → Cursor → `digest.md`)

This repo runs a GitHub Action once a week (or on-demand) that:

1. pulls new items from a list of journal RSS feeds  
2. uses the Cursor CLI to triage which items match your research interests  
3. writes a ranked digest to `digest.md` and commits it back to the repo

It’s meant to be forked and customized.

This was almost entirely vibe-coded as an exercise (I'm pleased at how well it works!)

---

## What’s in this repo

- **`digest.py`** — the pipeline (fetch RSS → filter → Cursor triage → render markdown)
- **`feeds.txt`** — RSS feed list (supports comments; optionally supports `Name | URL`)
- **`interests.md`** — your keywords + narrative seed (used for relevance)
- **`prompt.txt`** — the prompt template (easy to tune without editing Python)
- **`digest.md`** — generated output (auto-updated)
- **`.github/workflows/weekly-digest.yml`** — scheduled GitHub Action runner
- **`requirements.txt`** — Python dependencies

---

## Quick start (fork + run)

### 1) Fork the repo
- Click **Fork** on GitHub to copy this repo into your account.

### 2) Cursor CLI and API key
Ensure the **Cursor CLI** (`cursor` or `agent`) is installed and on `PATH` where the digest runs (e.g. your machine for local runs; for GitHub Actions you must use a runner or step that provides it). Get your API key from Cursor settings.

**Important:** never commit this key to the repo.

### 3) Add the API key as a GitHub Actions secret
In your forked repo:
- Go to **Settings → Secrets and variables → Actions**
- Click **New repository secret**
- Name: `CURSOR_API_KEY`
- Value: paste your Cursor API key

GitHub will inject it into the workflow at runtime.

### 4) Configure your feeds
Edit **`feeds.txt`**.

You can use comments:

```txt
# Core journals
Nature Neuroscience | https://www.nature.com/neuro.rss
PLOS Biology | https://journals.plos.org/plosbiology/rss

# Preprints
bioRxiv neuroscience | https://www.biorxiv.org/rss/subject/neuroscience.xml
