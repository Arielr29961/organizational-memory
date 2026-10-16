"""Choosing which sources from OTHER topics are worth sending to Ask AI.

Claude picks them by relevance to the question from a compact index of all sources, so a source does not need to
share a tag with the current topic. If that call fails, we fall back to the older rule (shared tags).
"""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from .. import models
from . import claude_service, tag_utils

log = logging.getLogger(__name__)

MAX_INDEX_SOURCES = 400  # most recent sources of other topics offered to the model
MAX_SELECTED = 8


def build_index(db: Session, topic_id: str, topic_tag_keys: set[str], topic_ids: set[str]) -> list[dict]:
    """Compact entries for sources of the user's other accessible topics, newest first. Keys s1, s2... are what the model refers to."""
    others = (
        db.query(models.Source)
        .filter(models.Source.topic_id != topic_id, models.Source.topic_id.in_(topic_ids))
        .order_by(models.Source.date.desc())
        .limit(MAX_INDEX_SOURCES)
        .all()
    )
    index = []
    for i, source in enumerate(others, start=1):
        tags = [st.tag.name for st in source.tags]
        index.append(
            {
                "key": f"s{i}",
                "source": source,
                "tags": tags,
                "shared_tags": [t for t in tags if tag_utils.tag_key(t) in topic_tag_keys],
            }
        )
    return index


def shared_tag_sources(index: list[dict]) -> list[models.Source]:
    """The older rule: sources of other topics that share at least one tag with the current topic."""
    return [entry["source"] for entry in index if entry["shared_tags"]]


def tagged_sources(index: list[dict], tag_name: str) -> list[models.Source]:
    """Focus mode: sources of the other accessible topics that carry this tag (no model call)."""
    key = tag_utils.tag_key(tag_name)
    return [e["source"] for e in index if any(tag_utils.tag_key(t) == key for t in e["tags"])][:MAX_SELECTED]


def select_sources(
    index: list[dict],
    topic_name: str,
    topic_description: Optional[str],
    questions: list[str],
) -> tuple[list[models.Source], bool]:
    """Returns (sources, used_ai). Falls back to shared-tag matching when the model call is unavailable or invalid."""
    if not index:
        return [], False
    try:
        raw = claude_service.select_related_sources(topic_name, topic_description, questions, index)
        by_key = {entry["key"]: entry["source"] for entry in index}
        chosen = []
        for key in (raw or {}).get("source_ids", []) or []:
            if key in by_key and by_key[key] not in chosen:
                chosen.append(by_key[key])
        return chosen[:MAX_SELECTED], True
    except Exception as exc:  # network error, bad JSON, no API key... Ask AI itself will report real problems
        log.warning("AI source selection failed, using shared tags instead: %s", exc)
        return shared_tag_sources(index)[:MAX_SELECTED], False
