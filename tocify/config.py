"""Shared environment-backed runtime configuration for tocify pipelines."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


def env_bool(name: str, default: bool, environ: Mapping[str, str] | None = None) -> bool:
    """Return boolean env value using common truthy spellings."""
    source = environ or os.environ
    raw = source.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def env_int(name: str, default: int, environ: Mapping[str, str] | None = None) -> int:
    """Return integer env value, falling back to default on parse errors."""
    source = environ or os.environ
    raw = source.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_float(name: str, default: float, environ: Mapping[str, str] | None = None) -> float:
    """Return float env value, falling back to default on parse errors."""
    source = environ or os.environ
    raw = source.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class PipelineConfig:
    """Core pipeline values shared by digest and runner weekly flows."""

    max_items_per_feed: int
    max_total_items: int
    lookback_days: int
    summary_max_chars: int
    prefilter_keep_top: int
    batch_size: int
    min_score_read: float
    max_returned: int


def load_pipeline_config(environ: Mapping[str, str] | None = None) -> PipelineConfig:
    """Load shared pipeline configuration from environment."""
    return PipelineConfig(
        max_items_per_feed=env_int("MAX_ITEMS_PER_FEED", 50, environ),
        max_total_items=env_int("MAX_TOTAL_ITEMS", 400, environ),
        lookback_days=env_int("LOOKBACK_DAYS", 7, environ),
        summary_max_chars=env_int("SUMMARY_MAX_CHARS", 500, environ),
        prefilter_keep_top=env_int("PREFILTER_KEEP_TOP", 200, environ),
        batch_size=env_int("BATCH_SIZE", 50, environ),
        min_score_read=env_float("MIN_SCORE_READ", 0.65, environ),
        max_returned=env_int("MAX_RETURNED", 40, environ),
    )
