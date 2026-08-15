"""A JSON file store.

Stands in for DynamoDB until the eval harness shows which access patterns
matter. Events are held in one object keyed by Event.id, so re-ingesting the
same listing overwrites rather than duplicates — the same idempotence a
DynamoDB put on the natural key would give.
"""

import json
import os
from collections.abc import Iterable
from pathlib import Path

from distillery.models import Event

DEFAULT_PATH = Path.home() / ".distillery" / "events.json"
PATH_ENV_VAR = "DISTILLERY_STORE_PATH"


def default_path() -> Path:
    override = os.environ.get(PATH_ENV_VAR)
    return Path(override) if override else DEFAULT_PATH


class JsonStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_path()

    def _read(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        with self.path.open(encoding="utf-8") as handle:
            return json.load(handle)

    def save(self, events: Iterable[Event]) -> tuple[int, int]:
        """Upsert events. Returns (written, of which new)."""
        stored = self._read()
        before = len(stored)

        written = 0
        for event in events:
            stored[event.id] = event.model_dump(mode="json")
            written += 1

        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a sibling then rename, so an interrupted run cannot leave a
        # half-written file where the next read expects valid JSON.
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(stored, handle, indent=2, ensure_ascii=False)
        temporary.replace(self.path)

        return written, len(stored) - before

    def all(self) -> list[Event]:
        return [Event.model_validate(row) for row in self._read().values()]

    def search(self, query: str, limit: int = 20) -> list[Event]:
        """Case-insensitive substring match over the fields a person would type."""
        needle = query.strip().lower()
        matches = [event for event in self.all() if _matches(event, needle)]
        matches.sort(key=lambda event: event.starts_at)
        return matches[:limit]


def _matches(event: Event, needle: str) -> bool:
    if not needle:
        return True
    haystack = [event.title, event.venue or "", *event.tags, *event.artists]
    return any(needle in field.lower() for field in haystack)
