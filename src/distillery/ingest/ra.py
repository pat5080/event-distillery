"""Resident Advisor adapter.

The public listing pages sit behind DataDome and return 403, but ra.co/graphql
answers normally and is not among the paths robots.txt disallows. Introspection
is enabled on that endpoint, so the query below was built from the published
schema rather than reverse-engineered.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from distillery.models import Category, Event, Source

ENDPOINT = "https://ra.co/graphql"
BASE_URL = "https://ra.co"
USER_AGENT = "event-distillery/0.1 (personal weekly listings tool)"

# Multi-city is out of scope, so areas are a lookup rather than a live query:
# one fewer request per run, and the timezone has to be stated somewhere.
AREAS: dict[str, tuple[int, str]] = {
    "london": (13, "Europe/London"),
}

LISTINGS_QUERY = """
query Listings($filters: FilterInputDtoInput, $page: Int, $pageSize: Int) {
  eventListings(filters: $filters, page: $page, pageSize: $pageSize) {
    totalResults
    data {
      id
      listingDate
      event {
        id
        title
        date
        startTime
        endTime
        contentUrl
        cost
        attending
        venue { name area { name country { name } } }
        genres { name }
        artists { name }
      }
    }
  }
}
"""


class UnknownCityError(ValueError):
    """Raised for a city with no configured RA area."""


def _window(days: int, now: datetime) -> tuple[str, str]:
    start = now.strftime("%Y-%m-%dT00:00:00.000Z")
    end = (now + timedelta(days=days)).strftime("%Y-%m-%dT00:00:00.000Z")
    return start, end


def fetch_page(
    client: httpx.Client,
    area_id: int,
    date_from: str,
    date_to: str,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    """Return one page of listing rows and the total the filter matched."""
    variables = {
        "filters": {
            "areas": {"eq": area_id},
            "listingDate": {"gte": date_from, "lte": date_to},
        },
        "page": page,
        "pageSize": page_size,
    }
    response = client.post(
        ENDPOINT,
        json={"query": LISTINGS_QUERY, "variables": variables},
        headers={"User-Agent": USER_AGENT, "Referer": f"{BASE_URL}/events/uk/london"},
    )
    response.raise_for_status()
    payload = response.json()

    if payload.get("errors"):
        raise RuntimeError(f"RA GraphQL error: {payload['errors']}")

    listings = payload["data"]["eventListings"]
    return listings["data"], listings["totalResults"]


def to_event(row: dict[str, Any], city: str, timezone: str, ingested_at: datetime) -> Event:
    """Map one listing row onto an Event.

    RA sends wall-clock times with no offset, so the zone is attached here.
    Event rejects naive datetimes, which keeps that omission from passing
    silently.
    """
    raw_event = row["event"]
    zone = ZoneInfo(timezone)

    starts_at = datetime.fromisoformat(raw_event["startTime"]).replace(tzinfo=zone)
    end_time = raw_event.get("endTime")
    ends_at = datetime.fromisoformat(end_time).replace(tzinfo=zone) if end_time else None

    venue = raw_event.get("venue") or {}

    return Event(
        source=Source.RA,
        source_id=str(raw_event["id"]),
        title=raw_event["title"],
        url=f"{BASE_URL}{raw_event['contentUrl']}",
        city=city,
        category=Category.MUSIC,
        starts_at=starts_at,
        timezone=timezone,
        ends_at=ends_at,
        venue=venue.get("name"),
        artists=[a["name"] for a in raw_event.get("artists") or []],
        tags=[g["name"] for g in raw_event.get("genres") or []],
        raw=row,
        ingested_at=ingested_at,
    )


def fetch_events(
    city: str,
    days: int = 7,
    page: int = 1,
    page_size: int = 50,
    client: httpx.Client | None = None,
    now: datetime | None = None,
) -> tuple[list[Event], int]:
    """Fetch one page of listings for a city.

    Returns the events that parsed and a count of the rows that did not. A
    single malformed listing should not lose the rest of the run.
    """
    key = city.lower()
    if key not in AREAS:
        raise UnknownCityError(f"no RA area configured for {city!r}")

    area_id, timezone = AREAS[key]
    ingested_at = now or datetime.now(UTC)
    date_from, date_to = _window(days, ingested_at)

    owns_client = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        rows, _total = fetch_page(client, area_id, date_from, date_to, page, page_size)
    finally:
        if owns_client:
            client.close()

    return _parse_rows(rows, key, timezone, ingested_at)


def _parse_rows(
    rows: list[dict[str, Any]], city: str, timezone: str, ingested_at: datetime
) -> tuple[list[Event], int]:
    events, failed = [], 0
    for row in rows:
        try:
            events.append(to_event(row, city, timezone, ingested_at))
        except Exception:  # noqa: BLE001 — one bad listing must not end the run
            failed += 1
    return events, failed


def iter_pages(total: int, page_size: int) -> Iterator[int]:
    """Page numbers covering total results. Unused until paging is turned on."""
    return iter(range(1, -(-total // page_size) + 1))
