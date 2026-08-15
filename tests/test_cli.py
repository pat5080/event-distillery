import pytest

from distillery.cli import build_parser, main


def test_ingest_parses_city_and_source():
    args = build_parser().parse_args(["ingest", "--city", "london", "--source", "ra"])
    assert args.city == "london"
    assert args.source == "ra"


def test_search_parses_query():
    args = build_parser().parse_args(["search", "ambient"])
    assert args.query == "ambient"


def test_unknown_source_is_rejected():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["ingest", "--city", "london", "--source", "nope"])


def test_missing_subcommand_is_rejected():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_stub_reports_not_implemented(capsys):
    assert main(["search", "ambient"]) == 1
    assert "not implemented" in capsys.readouterr().err
