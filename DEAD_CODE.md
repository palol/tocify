# Dead code marked for removal

This document lists code identified as unused (dead) and safe to remove. Imports marked below have been removed in code; the rest are documented for optional cleanup.

---

## Marked for removal

None currently. (Any new dead code found by linters should be listed here.)

A full dead-code review was done across the codebase; no new dead code was identified, so the above is intentional.

---

## Already removed (no longer in tree)

The following were previously listed as "marked for removal"; the code no longer exists in the repo:

- **`tocify/runner/vault.py`**: constants `CONFIG_DIR`, `CONTENT_DIR`, `BRIEFS_DIR`, `LOGS_DIR`, `TOPICS_DIR` — were never referenced; all code uses `get_topic_paths()` which builds paths from `root`. Removed.
- **`tocify/runner/cli.py`**: `import os` — was never used. Removed.

---

## Removed (done)

### Unused imports

- **`tocify/runner/weekly.py`**
  - `import subprocess` — never used (link resolution uses `importlib.util`, not subprocess).
  - `from urllib.parse import urlparse, parse_qs, urlencode, urlunparse` — never used.
  - `import math` — never used (no `math.` calls in this file).

- **`tocify/runner/cli.py`**
  - `import subprocess` — never used.
  - `parse_week_spec` from `tocify.runner.weekly` — removed (only used inside `run_weekly`).

- **`tocify/runner/weekly.py`**
  - `time as dt_time` from `datetime` — never used.

- **`tests/test_integrations_shared.py`**
  - `import json` — never used.

---

## Optional / non-code

- **`tests/__init__.py`** — empty file. Kept because tests are run as a package (`from tests.runner_test_utils import ...`); removing it breaks collection. Harmless to keep.

---

## Verified as used (not dead)

- **`tocify/digest.py`**: `section`, `sha1`, `parse_date` — used only inside this module (e.g. by `parse_interests_md`, `fetch_rss_items`).
- **`tocify/frontmatter.py`**: `parse_frontmatter`, `render_frontmatter` — used by `split_frontmatter_and_body` and `with_frontmatter`.
- **`tocify/integrations/_shared.py`**: `load_prompt_template` — used by `build_triage_prompt`.
- **`tocify/runner/link_hygiene.py`**: `_dedupe_urls` — used in this module and imported by `weekly.py`.
- **`tocify/runner/vault.py`**: `load_briefs_for_date_range`, `load_monthly_roundups_for_year`, `run_backend_prompt`, `run_structured_prompt`, `run_agent_and_save_output` — used by monthly, annual, weekly, and tests.
- **`tests/runner_test_utils.py`**: `write_runner_inputs` — used by test_topic_redundant_mentions, test_weekly_link_resolution, test_topic_gardener_default_behavior.

No unused functions, classes, or modules were found beyond the imports above.
