import json
from datetime import UTC, date, datetime

import httpx
import pytest

from distillery.ingest.ra import (
    LISTINGS_QUERY,
    UnknownCityError,
    _parse_rows,
    fetch_events,
    fetch_page,
    to_event,
)

INGESTED_AT = datetime(2026, 8, 15, 9, 0, tzinfo=UTC)

# Trimmed from a real response captured while probing the endpoint.
ROW = {
    "id": "12457152",
    "listingDate": "2026-08-15T00:00:00.000",
    "event": {
        "id": "2457152",
        "title": "Cooking with Palms Trax",
        "date": "2026-08-15T00:00:00.000",
        "startTime": "2026-08-15T13:00:00.000",
        "endTime": "2026-08-16T05:00:00.000",
        "contentUrl": "/events/2457152",
        "cost": "£10+",
        "attending": 2674,
        "venue": {"name": "The Cause", "area": {"name": "London"}},
        "genres": [{"name": "House"}, {"name": "Disco"}],
        "artists": [{"name": "Palms Trax"}, {"name": "Call Super"}],
    },
}


def convert(row=None):
    return to_event(row or ROW, "london", "Europe/London", INGESTED_AT)


def test_core_fields_are_mapped():
    event = convert()
    assert event.id == "ra:2457152"
    assert event.title == "Cooking with Palms Trax"
    assert event.venue == "The Cause"
    assert event.artists == ["Palms Trax", "Call Super"]


def test_relative_content_url_is_absolutised():
    assert convert().url == "https://ra.co/events/2457152"


def test_wall_clock_time_gets_the_local_zone_attached():
    """RA sends 13:00 with no offset. In August that is 12:00 UTC, not 13:00."""
    event = convert()
    assert event.starts_at == datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    assert event.ends_at == datetime(2026, 8, 16, 4, 0, tzinfo=UTC)
    assert event.local_date == date(2026, 8, 15)


def test_genres_become_normalised_tags():
    assert convert().tags == ["house", "disco"]


def test_raw_retains_fields_the_model_does_not_carry():
    raw_event = convert().raw["event"]
    assert raw_event["cost"] == "£10+"
    assert raw_event["attending"] == 2674


def test_missing_venue_is_tolerated():
    row = {**ROW, "event": {**ROW["event"], "venue": None}}
    assert convert(row).venue is None


def test_a_bad_row_is_counted_not_raised():
    broken = {"id": "x", "event": {"id": "1", "title": "No start time"}}
    events, failed = _parse_rows([ROW, broken, ROW], "london", "Europe/London", INGESTED_AT)
    assert len(events) == 2
    assert failed == 1


def test_unknown_city_is_rejected():
    with pytest.raises(UnknownCityError, match="paris"):
        fetch_events("paris")


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_page_sends_the_expected_filter():
    captured = {}

    def handler(request):
        captured.update(json.loads(request.read()))
        return httpx.Response(
            200, json={"data": {"eventListings": {"data": [ROW], "totalResults": 423}}}
        )

    with _client(handler) as client:
        rows, total = fetch_page(client, 13, "2026-08-15T00:00:00.000Z", "2026-08-22T00:00:00.000Z")

    assert total == 423
    assert len(rows) == 1

    filters = captured["variables"]["filters"]
    assert filters["areas"] == {"eq": 13}
    assert filters["listingDate"]["gte"] == "2026-08-15T00:00:00.000Z"
    assert captured["variables"]["pageSize"] == 50
    assert "eventListings" in LISTINGS_QUERY


def test_graphql_errors_are_raised():
    def handler(request):
        return httpx.Response(200, json={"errors": [{"message": "nope"}]})

    with _client(handler) as client, pytest.raises(RuntimeError, match="nope"):
        fetch_page(client, 13, "a", "b")


def test_http_errors_are_raised():
    def handler(request):
        return httpx.Response(403, text="blocked")

    with _client(handler) as client, pytest.raises(httpx.HTTPStatusError):
        fetch_page(client, 13, "a", "b")


def test_fetch_events_returns_parsed_events():
    def handler(request):
        return httpx.Response(
            200, json={"data": {"eventListings": {"data": [ROW], "totalResults": 1}}}
        )

    with _client(handler) as client:
        events, failed = fetch_events("london", client=client, now=INGESTED_AT)

    assert failed == 0
    assert events[0].id == "ra:2457152"
    assert events[0].city == "london"
