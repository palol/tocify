"""tocify.runner — Vault/multi-topic runner (weekly digest, monthly roundup, topic redundancy, gardener)."""

from tocify.runner.vault import (
    get_topic_paths,
    list_topics,
    TopicPaths,
    VAULT_ROOT,
)

__all__ = [
    "get_topic_paths",
    "list_topics",
    "TopicPaths",
    "VAULT_ROOT",
]
