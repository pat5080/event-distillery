"""Command-line entry point for Event Distillery."""

import argparse
import sys

SOURCES = ("ra",)


def run_ingest(args: argparse.Namespace) -> int:
    print(
        f"ingest not implemented yet (city={args.city}, source={args.source})",
        file=sys.stderr,
    )
    return 1


def run_search(args: argparse.Namespace) -> int:
    print(f"search not implemented yet (query={args.query!r})", file=sys.stderr)
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="distillery",
        description=__doc__,
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    ingest = subcommands.add_parser("ingest", help="fetch and store events from a source")
    ingest.add_argument("--city", required=True, help="city to ingest, e.g. london")
    ingest.add_argument(
        "--source", required=True, choices=SOURCES, help="listing source to fetch from"
    )
    ingest.set_defaults(handler=run_ingest)

    search = subcommands.add_parser("search", help="search stored events")
    search.add_argument("query", help='free-text query, e.g. "ambient"')
    search.set_defaults(handler=run_search)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
