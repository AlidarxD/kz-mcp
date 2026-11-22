"""`kz-mcp` command line entry point."""

from __future__ import annotations

import argparse
import logging
import sys

from kz_mcp import __version__


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="kz-mcp", description=__doc__)
    parser.add_argument(
        "--transport",
        choices=["stdio"],
        default="stdio",
        help="MCP transport (Streamable HTTP arrives in a later release)",
    )
    parser.add_argument("--version", action="version", version=f"kz-mcp {__version__}")
    args = parser.parse_args(argv)

    from kz_mcp.server import build_server
    from kz_mcp.settings import Settings

    settings = Settings()
    # stdout carries the protocol in stdio mode: logs go to stderr only.
    logging.basicConfig(
        level=settings.log_level,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    build_server(settings).run(args.transport)
