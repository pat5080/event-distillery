from datetime import UTC, datetime

import pytest

from distillery.models import Category, Event, Source
from distillery.store import PATH_ENV_VAR, JsonStore, default_path


def make_event(source_id="1", title="Ambient night", **overrides) -> Event:
    fields = {
        "source": Source.RA,
        "source_id": source_id,
        "title": title,
        "url": f"https://ra.co/events/{source_id}",
        "city": "london",
        "category": Category.MUSIC,
        "starts_at": datetime(2026, 8, 21, 22, 0, tzinfo=UTC),
        "timezone": "Europe/London",
        "ingested_at": datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
    }
    return Event(**(fields | overrides))


@pytest.fixture
def store(tmp_path):
    return JsonStore(tmp_path / "events.json")


def test_saved_events_survive_a_new_store_instance(store):
    store.save([make_event()])
    assert JsonStore(store.path).all()[0].id == "ra:1"


def test_reingesting_the_same_event_overwrites_rather_than_duplicates(store):
    store.save([make_event(title="Old title")])
    written, added = store.save([make_event(title="New title")])

    assert (written, added) == (1, 0)
    stored = store.all()
    assert len(stored) == 1
    assert stored[0].title == "New title"


def test_new_events_are_counted_separately(store):
    store.save([make_event("1")])
    written, added = store.save([make_event("1"), make_event("2")])
    assert (written, added) == (2, 1)


def test_search_matches_title_tags_venue_and_artists(store):
    store.save(
        [
            make_event("1", title="Ambient night"),
            make_event("2", title="Techno night", tags=["Drone"]),
            make_event("3", title="Jazz night", venue="The Ambient Rooms"),
            make_event("4", title="Disco night", artists=["Ambient Jones"]),
            make_event("5", title="Nothing relevant"),
        ]
    )
    assert {e.source_id for e in store.search("ambient")} == {"1", "3", "4"}
    assert {e.source_id for e in store.search("drone")} == {"2"}


def test_search_is_case_insensitive(store):
    store.save([make_event(title="Ambient Night")])
    assert len(store.search("AMBIENT")) == 1


def test_search_returns_results_in_start_order(store):
    store.save(
        [
            make_event("late", starts_at=datetime(2026, 8, 22, 22, 0, tzinfo=UTC)),
            make_event("early", starts_at=datetime(2026, 8, 20, 22, 0, tzinfo=UTC)),
        ]
    )
    assert [e.source_id for e in store.search("ambient")] == ["early", "late"]


def test_search_respects_the_limit(store):
    store.save([make_event(str(i)) for i in range(10)])
    assert len(store.search("ambient", limit=3)) == 3


def test_reading_a_store_that_does_not_exist_yet_is_empty(store):
    assert store.all() == []


def test_computed_fields_round_trip_through_the_file(store):
    store.save([make_event()])
    restored = store.all()[0]
    assert restored.id == "ra:1"
    assert restored.local_date == make_event().local_date


def test_path_comes_from_the_environment_when_set(monkeypatch, tmp_path):
    monkeypatch.setenv(PATH_ENV_VAR, str(tmp_path / "custom.json"))
    assert default_path() == tmp_path / "custom.json"


def test_an_interrupted_write_leaves_no_temporary_file(store):
    store.save([make_event()])
    assert not store.path.with_suffix(".tmp").exists()
