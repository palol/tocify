# tocify — Weekly Journal ToC Digest (RSS → triage → `digest.md`)

This repo runs a GitHub Action once a week (or on-demand) that:

1. pulls new items from a list of journal RSS feeds  
2. triages items against your research interests (OpenAI API or Cursor CLI)  
3. writes a ranked digest to `digest.md` and commits it back to the repo

It’s meant to be forked and customized.

---

## What’s in this repo

- **`digest.py`** — pipeline (fetch RSS → filter → triage → render markdown)
- **`integrations/`** — optional Cursor CLI triage backend (default: in-file OpenAI in digest.py)
- **`feeds.txt`** — RSS feed list (comments; optional `Name | URL`)
- **`interests.md`** — keywords + narrative (used for relevance)
- **`prompt.txt`** — prompt template (used by OpenAI and Cursor backends)
- **`digest.md`** — generated output (auto-updated)
- **`.github/workflows/weekly-digest.yml`** — scheduled GitHub Action
- **`requirements.txt`** — Python dependencies (includes `selectolax` for the HTML adapter)
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

Backend is auto-chosen from which key is set, or set **`TOCIFY_BACKEND=openai`** or **`cursor`** to force.

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

### HTML adapter (opt-in)

Some sources (company news pages, etc.) don't publish RSS. tocify ships an
HTML adapter behind a feature flag. Enable with:

```bash
export TOCIFY_ENABLE_HTML=1
```

Then add lines to `feeds.txt` with a third `| TYPE [selectors]` field:

```txt
# Type defaults to `rss`. Use `html` for non-feed pages.
Paradromics | https://www.paradromics.com/news | html
Synchron | https://synchron.com/news | html item="a[href*='/news/']" title="h3"
Science Corp | https://science.xyz | html item="div[class*=card]" title=".title" link="a@href" date="time@datetime"
```

**Selector keys** (all optional; sensible defaults are tried):

| Key | Meaning | Example |
|---|---|---|
| `item` | repeating element | `article`, `li.post`, `div[class*=card]` |
| `title` | item title | `h2, h3, .title` |
| `link` | item URL — usually `a@href` | `a@href` |
| `date` | publish date (parsed via dateutil) | `time@datetime` |
| `summary` | item blurb | `p.excerpt` |

Append `@attr` to any selector to pull an attribute (e.g. `time@datetime`,
`a@href`) instead of the element's text.

**Env knobs:**

- `TOCIFY_ENABLE_HTML` — `1` to enable HTML adapter (default `0`)
- `TOCIFY_HTML_TIMEOUT` — seconds per request (default `20`)
- `TOCIFY_HTML_USER_AGENT` — override request UA

Limitations (v1): no JavaScript rendering (SPA pages like neuralink.com/updates
yield nothing); no item-page fetch (dates must appear on the index page or items
bypass the lookback cutoff).
