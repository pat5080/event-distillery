from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from distillery.models import Category, Enrichment, Event, Source


def make_event(**overrides) -> Event:
    fields = {
        "source": Source.RA,
        "source_id": "12345",
        "title": "Ambient night",
        "url": "https://ra.co/events/12345",
        "city": "london",
        "category": Category.MUSIC,
        "starts_at": datetime(2026, 8, 21, 22, 0, tzinfo=UTC),
        "timezone": "Europe/London",
        "ingested_at": datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
    }
    return Event(**(fields | overrides))


def test_id_is_source_scoped():
    assert make_event().id == "ra:12345"


def test_naive_datetime_is_rejected():
    with pytest.raises(ValidationError, match="timezone-aware"):
        make_event(starts_at=datetime(2026, 8, 21, 22, 0))  # noqa: DTZ001 — the point of the test


def test_non_utc_input_is_coerced_to_utc():
    event = make_event(starts_at=datetime(2026, 8, 21, 23, 0, tzinfo=ZoneInfo("Europe/London")))
    assert event.starts_at == datetime(2026, 8, 21, 22, 0, tzinfo=UTC)


def test_unknown_timezone_is_rejected():
    with pytest.raises(ValidationError, match="unknown IANA timezone"):
        make_event(timezone="Europe/Narnia")


def test_local_date_diverges_from_the_utc_date_during_bst():
    """The case that makes local_date worth storing at all.

    23:30 UTC on a Friday in August is 00:30 Saturday in London. Filtering on
    the UTC date alone files this under Friday, so a "what's on Saturday"
    query would miss it.
    """
    event = make_event(starts_at=datetime(2026, 8, 21, 23, 30, tzinfo=UTC))
    assert event.starts_at.date() == date(2026, 8, 21)
    assert event.local_date == date(2026, 8, 22)


def test_local_date_outside_bst_matches_utc():
    event = make_event(starts_at=datetime(2026, 1, 15, 23, 30, tzinfo=UTC))
    assert event.local_date == date(2026, 1, 15)


def test_tags_are_lowercased_deduped_and_stripped():
    event = make_event(tags=["Ambient", " ambient ", "DRONE", "", "techno"])
    assert event.tags == ["ambient", "drone", "techno"]


def test_enrichment_defaults_to_absent():
    assert make_event().enrichment is None


def test_enrichment_does_not_touch_source_tags():
    event = make_event(
        tags=["ambient"],
        enrichment=Enrichment(summary="Quiet one", tags=["contemplative"]),
    )
    assert event.tags == ["ambient"]
    assert event.enrichment is not None
    assert event.enrichment.tags == ["contemplative"]


def test_computed_fields_survive_a_round_trip():
    event = make_event()
    dumped = event.model_dump()
    assert dumped["id"] == "ra:12345"
    assert dumped["local_date"] == date(2026, 8, 21)
    assert Event.model_validate(dumped).id == event.id
