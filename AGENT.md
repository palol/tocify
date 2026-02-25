# Agent context

For AI/contributor context only; user-facing docs are in README.md.

## Instructions 

You are a software engineer specialized in github actions, web scraping,
and llm applications.  You are also a multi-agent coordinator.

Your task is to modify the "tocify" repository to support the following change:

> Replace openai client with Cursor cli, which uses `CURSOR_API_KEY` and `cursor` cli commands
> Note that cursor responses are not structured, so the prompt template may need to be modified. 

Examples already available in @~/workspace/neural-noise/. 

This should be as minimal of a change for the tocify repo.

## Protocol

### Prep

> if `agent_plan.md` already exists, move on to next section

1. Inspect the tocify repository
2. Peek at neural-noise source code for Cursor cli examples
3. Summarize findings in agent_plan.md

### Plan

1. Based on findings in `agent_plan.md`, plan how to enable support for Cursor. 
2. If it helps, use the python library `newspaper`

## Scope

In: small, elegant code changes to the tocify repository. follow existing patterns. 

Out: massive, complicated changes. multi-modal/client support. 

## 2025-02-17

- **Turn**: User asked why CURSOR_API_KEY in .env was not being read. Cause: digest.py never called load_dotenv(). Implemented the plan by adding `from dotenv import load_dotenv` and `load_dotenv()` at the top of digest.py so .env is loaded before any os.getenv usage; CURSOR_API_KEY from .env is now read when running locally.

## 2025-02-17

- **Turn**: User asked to remove TOCIFY variables so the project is Cursor CLI only. Removed _cursor_cli() and TOCIFY_CURSOR_CLI; _cursor_api_key() now uses only CURSOR_API_KEY; error message updated; command is always `agent -p --output-format text --trust`.
- **Turn**: Cursor backend now passes the prompt via stdin (not argv) so agent (cursor-cli) does not hit "Argument list too long" on Linux when batches or runner prompts are large.
