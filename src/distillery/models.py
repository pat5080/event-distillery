"""The Event model, shared by the write and read paths so they cannot drift."""

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, computed_field, field_validator


class Source(StrEnum):
    RA = "ra"


class Category(StrEnum):
    MUSIC = "music"
    FILM = "film"
    CULTURE = "culture"


class Enrichment(BaseModel):
    """LLM-derived fields, kept apart from parsed source data.

    Nothing here may overwrite a field on Event: the eval harness compares an
    enrichment arm against arms that never see it, which is only possible while
    the two remain separable.
    """

    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    model: str | None = None
    generated_at: datetime | None = None


class Event(BaseModel):
    source: Source
    source_id: str

    title: str
    url: str
    city: str
    category: Category

    starts_at: datetime
    timezone: str

    ends_at: datetime | None = None
    venue: str | None = None
    artists: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    description: str | None = None

    raw: dict[str, Any] = Field(default_factory=dict)
    ingested_at: datetime

    enrichment: Enrichment | None = None

    @computed_field
    @property
    def id(self) -> str:
        return f"{self.source.value}:{self.source_id}"

    @computed_field
    @property
    def local_date(self) -> date:
        return self.starts_at.astimezone(ZoneInfo(self.timezone)).date()

    @field_validator("starts_at", "ends_at", "ingested_at")
    @classmethod
    def _to_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("must be timezone-aware; naive datetimes are ambiguous")
        return value.astimezone(UTC)

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown IANA timezone: {value!r}") from exc
        return value

    @field_validator("tags")
    @classmethod
    def _normalise_tags(cls, value: list[str]) -> list[str]:
        deduped = dict.fromkeys(t.strip().lower() for t in value)
        deduped.pop("", None)
        return list(deduped)
