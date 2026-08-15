from datetime import UTC, datetime

import httpx
import pytest

from distillery import cli
from distillery.ingest.ra import UnknownCityError
from distillery.models import Category, Event, Source
from distillery.store import PATH_ENV_VAR


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch, tmp_path):
    """Keep the CLI off the real store in ~/.distillery."""
    monkeypatch.setenv(PATH_ENV_VAR, str(tmp_path / "events.json"))


def make_event(source_id="1", title="Ambient night") -> Event:
    return Event(
        source=Source.RA,
        source_id=source_id,
        title=title,
        url=f"https://ra.co/events/{source_id}",
        city="london",
        category=Category.MUSIC,
        starts_at=datetime(2026, 8, 21, 22, 0, tzinfo=UTC),
        timezone="Europe/London",
        ingested_at=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
    )


def test_ingest_parses_city_and_source():
    args = cli.build_parser().parse_args(["ingest", "--city", "london", "--source", "ra"])
    assert (args.city, args.source, args.days) == ("london", "ra", 7)


def test_search_parses_query_and_limit():
    args = cli.build_parser().parse_args(["search", "ambient", "--limit", "5"])
    assert (args.query, args.limit) == ("ambient", 5)


def test_unknown_source_is_rejected():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["ingest", "--city", "london", "--source", "nope"])


def test_missing_subcommand_is_rejected():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])


def test_ingest_stores_events_and_reports_counts(monkeypatch, capsys):
    monkeypatch.setattr(cli, "fetch_events", lambda city, days: ([make_event()], 2))

    assert cli.main(["ingest", "--city", "london", "--source", "ra"]) == 0
    assert "ingested 1 events" in capsys.readouterr().out


def test_ingest_reports_an_unknown_city(monkeypatch, capsys):
    def boom(city, days):
        raise UnknownCityError("no RA area configured for 'paris'")

    monkeypatch.setattr(cli, "fetch_events", boom)

    assert cli.main(["ingest", "--city", "paris", "--source", "ra"]) == 1
    assert "no RA area configured" in capsys.readouterr().err


def test_ingest_reports_a_network_failure(monkeypatch, capsys):
    def boom(city, days):
        raise httpx.ConnectError("dns went away")

    monkeypatch.setattr(cli, "fetch_events", boom)

    assert cli.main(["ingest", "--city", "london", "--source", "ra"]) == 1
    assert "request failed" in capsys.readouterr().err


def test_search_before_any_ingest_explains_itself(capsys):
    assert cli.main(["search", "ambient"]) == 1
    assert "run `distillery ingest` first" in capsys.readouterr().err


def test_ingest_then_search_prints_the_event(monkeypatch, capsys):
    monkeypatch.setattr(cli, "fetch_events", lambda city, days: ([make_event()], 0))
    cli.main(["ingest", "--city", "london", "--source", "ra"])
    capsys.readouterr()

    assert cli.main(["search", "ambient"]) == 0
    assert "Ambient night" in capsys.readouterr().out


def test_search_with_no_matches_says_so(monkeypatch, capsys):
    monkeypatch.setattr(cli, "fetch_events", lambda city, days: ([make_event()], 0))
    cli.main(["ingest", "--city", "london", "--source", "ra"])
    capsys.readouterr()

    assert cli.main(["search", "gabber"]) == 0
    assert "no events matching" in capsys.readouterr().out
