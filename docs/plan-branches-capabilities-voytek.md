# Plan: Individual branches to submit capabilities to voytek/tocify

## Context

- **Your repo**: `origin` = `https://github.com/palol/tocify.git` (your fork); current branch `runner-module`. Your **main** is stuck as an open PR to the voytek repo.
- **Upstream / target**: **voytek/tocify** — the "original" tocify. All capability branches must target this repo and open PRs into `voytek/tocify:main`.
- **Backends**: Cursor and Gemini are already implemented in `tocify/integrations/` in your tree. The voytek repo may or may not have that code yet; either way, each capability branch should be a minimal, reviewable PR.
- **Gap**: GitHub Actions in voytek/tocify likely only wire OpenAI (or less). Cursor and Gemini need workflow + README support.

**Constraint**: Do **not** base capability branches on your main or runner-module. Each branch must start **fresh from voytek/tocify/main** so PRs are clean and not blocked by your existing PR.

---

## 1. Upstream and branch strategy

- **Add voytek as upstream** (if not already):
  ```bash
  git remote add upstream https://github.com/voytek/tocify.git
  ```
  (If the voytek repo URL differs, use its clone URL.) Keep `origin` as your fork (palol/tocify).

- **Fetch upstream**:
  ```bash
  git fetch upstream
  ```
  so you have `upstream/main` (or whatever voytek's default branch is; assume `main` here).

- **Every capability branch starts from voytek's main**:
  ```bash
  git checkout -b feature/cursor-backend upstream/main
  ```
  (and similarly `feature/gemini-backend`). Do not branch from `origin/main` or `runner-module` — those are ahead of or divergent from voytek/main and would make the PR huge or stuck.

- **One capability per branch**: each branch contains a single, reviewable change. Naming: e.g. `feature/cursor-backend`, `feature/gemini-backend`.

**Creating each branch (repeat for Cursor, then Gemini):**

```bash
git fetch upstream
git checkout -b feature/cursor-backend upstream/main   # or feature/gemini-backend
# make changes (cherry-pick or manually add only what voytek lacks)
git add -A && git commit -m "Add Cursor backend support (workflow + docs)"
git push origin feature/cursor-backend
# open PR: palol/tocify feature/cursor-backend → voytek/tocify main
```

---

## 2. Branch 1: Cursor backend support

**Scope**: Ensure the **Cursor** backend is fully supported and documented for the original tocify (digest + runner).

**Already in code** (no code split needed if original has no Cursor):

- `tocify/integrations/cursor_cli.py` — Cursor CLI triage + completion
- `tocify/integrations/__init__.py` — registry `cursor`, default when `CURSOR_API_KEY` set
- Runner and digest both use `get_triage_backend()` / `get_run_completion()` and thus already use Cursor when `TOCIFY_BACKEND=cursor`

**What to put in this branch** (branch created from `upstream/main` = voytek/tocify/main):

- **Code** (only if voytek/tocify does not yet have Cursor): Add `tocify/integrations/cursor_cli.py` and register `cursor` in `tocify/integrations/__init__.py`. If voytek already has it, skip or limit to workflow/docs.
- **Workflows**
  - **Digest**: Add or extend so Cursor is supported (e.g. a `weekly-digest-cursor.yml` or a Cursor job in the main digest workflow using `CURSOR_API_KEY` and Cursor CLI install).
  - **Runner**: If voytek has a runner workflow, add Cursor CLI install step and a job with `TOCIFY_BACKEND=cursor` and `CURSOR_API_KEY`.
- **Docs**
  - README: "Quick start (Cursor CLI)" with `CURSOR_API_KEY`, optional `TOCIFY_BACKEND=cursor`, and note that `agent` must be on `PATH` (and in CI, install step).
- **Dependencies**
  - No extra pip deps for Cursor (CLI is external).

**Deliverable**: One branch (e.g. `feature/cursor-backend`) created from voytek/tocify/main, that adds Cursor as a first-class backend for digest (and runner if present), with CI and README.

---

## 3. Branch 2: Gemini backend support

**Scope**: Ensure the **Gemini** backend is fully supported and documented (digest + runner + changelog polish).

**Already in code**:

- `tocify/integrations/gemini_triage.py` — triage + completion
- `tocify/integrations/__init__.py` — registry `gemini`; only used when `TOCIFY_BACKEND=gemini`
- `pyproject.toml` — `google-genai>=0.6.0` already present

**What to put in this branch** (branch created from `upstream/main` = voytek/tocify/main):

- **Code** (only if voytek/tocify does not yet have Gemini): Add `tocify/integrations/gemini_triage.py`, register `gemini` in `tocify/integrations/__init__.py`, and add `google-genai` to dependencies. If voytek already has it, skip or limit to workflow/docs.
- **Workflows**
  - **Digest**: Add a job (or workflow) that runs digest with `TOCIFY_BACKEND=gemini` and `GEMINI_API_KEY` secret (and optionally `GEMINI_MODEL`).
  - **Runner**: If voytek has a runner workflow, add a job with `TOCIFY_BACKEND=gemini`, `GEMINI_API_KEY`, and optionally `GEMINI_MODEL`. No CLI install (API only).
- **Docs**
  - README: "Quick start (Gemini)" with `GEMINI_API_KEY`, optional `GEMINI_MODEL`, and `TOCIFY_BACKEND=gemini`; note that Gemini is opt-in (only when explicitly set).

**Deliverable**: One branch (e.g. `feature/gemini-backend`) created from voytek/tocify/main, that adds Gemini as a first-class backend in CI and README.

---

## 4. Order and dependency

- **No strict dependency** between Cursor and Gemini branches; they can be two independent PRs.
- **Suggested order**: Cursor first, then Gemini (matches "starting with backend support for cursor, gemini"), and keeps each PR smaller.
- If voytek/tocify already has one of these backends in code but not in CI/docs, the corresponding branch only adds workflow + README changes.

---

## 5. Workflow structure (reference)

Current layout in your repo:

- `weekly-digest.yml` — OpenAI only
- `weekly-digest-cursor.yml` — Cursor-only digest
- `weekly-runner.yml` — two jobs: OpenAI (when `OPENAI_API_KEY`), Cursor (when `CURSOR_API_KEY` only); no Gemini job

For the original repo you can either:

- **Option A**: Add separate workflow files for Cursor and Gemini digest (like your `weekly-digest-cursor.yml`), plus extend the runner workflow with Cursor and Gemini jobs; or
- **Option B**: Single digest workflow and single runner workflow with multiple jobs (one per backend), guarded by `secrets.OPENAI_API_KEY != ''`, etc.

Either way, the two branches should introduce only the Cursor or only the Gemini additions so each PR is single-purpose.

---

## 6. Checklist before opening PRs

- Branch was created **from voytek/tocify/main** (`git checkout -b <branch> upstream/main` after `git fetch upstream`). Do not use your main or runner-module as base.
- One backend per branch; no mixing of Cursor and Gemini in the same branch.
- CI: workflow(s) run for the new backend (digest and/or runner as applicable).
- README: quick start and backend selection documented.
- Tests: existing tests (e.g. `tests/test_runner_backend_dispatch.py`, integration tests) still pass; add or adjust only if the original's test suite expects new coverage for the new backend.

---

## Summary

| Branch | Purpose | Main changes |
|--------|--------|--------------|
| `feature/cursor-backend` | Cursor backend support | Workflows (digest + runner) for Cursor, README quick start, ensure `agent` on PATH in CI |
| `feature/gemini-backend` | Gemini backend support | Workflows (digest + runner) for Gemini, README quick start, optional `GEMINI_MODEL` |

Code for both backends may already exist in your tree; on each branch (based on voytek/tocify/main) you add only what voytek is missing (integration code, workflows, README). Push the branch to your fork and open a PR into **voytek/tocify:main**.
