"""Command-line entry point for Event Distillery."""

import argparse
import sys

import httpx

from distillery.ingest.ra import UnknownCityError, fetch_events
from distillery.models import Event
from distillery.store import JsonStore

SOURCES = ("ra",)


def run_ingest(args: argparse.Namespace) -> int:
    try:
        events, failed = fetch_events(args.city, days=args.days)
    except UnknownCityError as exc:
        print(f"distillery: {exc}", file=sys.stderr)
        return 1
    except httpx.HTTPError as exc:
        print(f"distillery: {args.source} request failed: {exc}", file=sys.stderr)
        return 1

    written, added = JsonStore().save(events)
    print(f"ingested {written} events from {args.source} ({added} new, {failed} unparsed)")
    return 0


def run_search(args: argparse.Namespace) -> int:
    store = JsonStore()
    if not store.path.exists():
        print("distillery: nothing stored yet — run `distillery ingest` first", file=sys.stderr)
        return 1

    matches = store.search(args.query, limit=args.limit)
    if not matches:
        print(f"no events matching {args.query!r}")
        return 0

    for event in matches:
        print(_format(event))
    return 0


def _format(event: Event) -> str:
    local = event.starts_at.astimezone()
    when = f"{event.local_date} {local:%H:%M}"
    tags = ", ".join(event.tags[:3])
    return f"{when}  {event.title[:52]:54} {(event.venue or '')[:22]:24} {tags}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="distillery", description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    ingest = subcommands.add_parser("ingest", help="fetch and store events from a source")
    ingest.add_argument("--city", required=True, help="city to ingest, e.g. london")
    ingest.add_argument(
        "--source", required=True, choices=SOURCES, help="listing source to fetch from"
    )
    ingest.add_argument("--days", type=int, default=7, help="days ahead to fetch (default 7)")
    ingest.set_defaults(handler=run_ingest)

    search = subcommands.add_parser("search", help="search stored events")
    search.add_argument("query", help='free-text query, e.g. "ambient"')
    search.add_argument("--limit", type=int, default=20, help="results to show (default 20)")
    search.set_defaults(handler=run_search)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
