# Plan: GitHub issue #101 — Semantic Scholar API (`runner-module`)

## Repo and branch

- **Primary implementation:** [palol/tocify](https://github.com/palol/tocify), branch **`runner-module`** (tracks `origin/runner-module`).
- **Paths below** are relative to the **tocify repo root**.

Downstream consumers (e.g. **neural-noise**) only need a version/git pin bump after tocify merges; they are not where issue #101 is implemented.

## Problem (issue summary)

RSS + OpenAlex can **miss thesis / institutional** and other S2-heavy coverage. Semantic Scholar’s **`/graph/v1/paper/search`** returns structured JSON with query + **publicationDateOrYear**-style filtering.

Example:

`GET https://api.semanticscholar.org/graph/v1/paper/search?query=...&fields=title,year,authors,externalIds&publicationDateOrYear=2026`

## Code map (verified on `runner-module`)

| Role | File |
|------|------|
| Historical backends (OpenAlex, NewsAPI, …) | `tocify/historical.py` — `fetch_historical_items()`, loop over `backends` |
| Weekly orchestration: build `backends`, call `fetch_historical_items`, `merge_feed_items` | `tocify/runner/weekly.py` — `run_weekly()` ~lines 1383–1438 |
| Pattern for env-based HTTP backend + standard item schema | `tocify/news.py` |
| Test style (mock HTTP, assert schema / dates) | `tests/test_googlenews.py` |

Shared item fields (unchanged): `id`, `source`, `title`, `link`, `published_utc`, `summary`.

```mermaid
flowchart LR
  rss[fetch_rss_items] --> merge[merge_feed_items]
  hist[fetch_historical_items] --> merge
  merge --> prefilter[keyword_prefilter]
  prefilter --> triage[LLM triage]
```

## Checklist

- [ ] Add `tocify/semanticscholar.py` with `fetch_semantic_scholar_items()` (S2 JSON → standard item dicts; query, date window, pagination, optional `x-api-key`).
- [ ] Extend `tocify/historical.py` `fetch_historical_items()` with backend `semanticscholar` and env limits (`SEMANTIC_SCHOLAR_*`).
- [ ] In `tocify/runner/weekly.py` (~1383–1435): `WEEKLY_SEMANTIC_SCHOLAR` gate; pass `week_start` / `week_end` + `topic_search` into `fetch_historical_items`.
- [ ] Add `tests/test_semanticscholar.py` (mirror `tests/test_googlenews.py`: mocked requests, schema + date window).
- [ ] Bump tocify `pyproject.toml` version for release / pin.
- [ ] **Downstream (neural-noise):** bump tocify git ref, optional `content/readme.md` colophon, optional `weekly_brief.yml` env + API secret.

## Implementation steps (all in tocify)

### 1. `tocify/semanticscholar.py`

- `fetch_semantic_scholar_items(start_date, end_date, *, query: str | None, ...)` using `requests.get("https://api.semanticscholar.org/graph/v1/paper/search", ...)`.
- Query params: `query`, `fields` (e.g. `title`, `year`, `authors`, `publicationDate`, `url`, `externalIds`, `abstract`), pagination per [S2 API docs](https://api.semanticscholar.org/api-docs/).
- **Date filtering:** confirm `publicationDateOrYear` semantics (single year vs range). For ISO weeks spanning two calendar years, use **two API calls**, **client-side filter** on `publicationDate`, or documented range syntax—whichever matches the API.
- **`link`:** prefer `https://doi.org/{doi}` from `externalIds`; else S2 `url`.
- **`id`:** `sha1(f"Semantic Scholar|{title}|{link}")` (same pattern as other backends).
- **Env:** e.g. `SEMANTIC_SCHOLAR_API_KEY` / `S2_API_KEY` → header `x-api-key`; `SEMANTIC_SCHOLAR_TIMEOUT`, `SEMANTIC_SCHOLAR_MAX_ITEMS`, optional page size; on HTTP errors / empty body, warn and return `[]` like `news.py` when unconfigured.

### 2. `tocify/historical.py`

- Add `elif name == "semanticscholar":` importing `fetch_semantic_scholar_items` with the same query string as OpenAlex (simplest: reuse `openalex_search` kwarg for the search string, or add `semanticscholar_query` if you prefer an explicit name).
- Update module/docstring list of backend names.

### 3. `tocify/runner/weekly.py`

- `WEEKLY_SEMANTIC_SCHOLAR` via `env_bool` (choose default explicitly: **off** avoids surprise 429s without a key; **on** matches `WEEKLY_OPENALEX` aggressiveness—document in commit).
- If enabled and `topic_search` non-empty: `backends.append("semanticscholar")` and pass query into `fetch_historical_items(...)`.

### 4. Tests

- `tests/test_semanticscholar.py` — mock `requests.get`, assert normalized items and that dates outside `start_date`–`end_date` are dropped if filtering is client-side.

### 5. Version

- Bump `pyproject.toml` / package version in tocify for a releasable tag or neural-noise pin.

## Downstream (neural-noise) — after tocify ships

- Bump tocify git ref in `pyproject.toml`, `uv lock`.
- Optional: `content/readme.md` colophon; `WEEKLY_SEMANTIC_SCHOLAR` + secret in `.github/workflows/weekly_brief.yml`.

## Non-goals

- DOI-level dedupe across OpenAlex vs S2 (same work, different URLs).
- Replacing OpenAlex; S2 is **additive**.

## Risks

- **Rate limits / 429** without API key; graceful empty return + warning.
- **Duplicate narratives** in triage if both OpenAlex and S2 return the same paper under different links.

## Implementation hygiene

When implementing, use the **checkpoint worktree** workflow on **tocify** (`runner-module`) separately from any neural-noise bump.
