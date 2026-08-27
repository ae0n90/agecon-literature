"""Explicit setup, diagnosis, and MCP serving commands."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Literal

from .config import CONFIG_ENV, default_config_path, load_settings
from .server import create_server
from .service import LiteratureService
from .tool_catalog import TOOL_CATALOG


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agecon-literature",
        description="Local-first CNKI discovery and Zotero 10 Local API MCP",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=f"TOML path (or set {CONFIG_ENV}); default: {default_config_path()}",
    )
    commands = parser.add_subparsers(dest="command")

    serve = commands.add_parser("serve", help="start the MCP server")
    serve.add_argument("--transport", choices=["stdio", "http", "sse"], default="stdio")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=7790)

    commands.add_parser("doctor", help="inspect local prerequisites without writes")
    commands.add_parser("tools", help="print the public tool catalog")
    commands.add_parser("paths", help="print configuration and runtime paths")

    cnki = commands.add_parser("cnki-init", help="interactively initialize a CNKI profile")
    cnki.add_argument("--profile", default=None)

    commands.add_parser(
        "zotero-probe",
        help="read Zotero Local API identity without requesting write access",
    )
    commands.add_parser(
        "zotero-authorize",
        help="ask Zotero for a remembered write key and store it in the OS keychain",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command is None:
        args.command = "serve"
        args.transport = "stdio"
        args.host = "127.0.0.1"
        args.port = 7790
    settings = load_settings(args.config)

    if args.command == "serve":
        if args.host not in {"127.0.0.1", "localhost", "::1"}:
            parser.error("network transports must bind to loopback")
        server = create_server(settings, host=args.host, port=args.port)
        transport: Literal["stdio", "sse", "streamable-http"]
        if args.transport == "http":
            transport = "streamable-http"
        elif args.transport == "sse":
            transport = "sse"
        else:
            transport = "stdio"
        try:
            server.run(transport=transport)
        except KeyboardInterrupt:
            return 0
        return 0

    service = LiteratureService(settings)
    try:
        if args.command == "doctor":
            _print(service.doctor())
        elif args.command == "tools":
            _print({"tools": TOOL_CATALOG})
        elif args.command == "paths":
            _print(
                {
                    "config": str(args.config or default_config_path()),
                    "data_dir": str(settings.data_dir),
                    "database": str(settings.database_path),
                    "downloads": str(settings.downloads_dir),
                    "exports": str(settings.exports_dir),
                }
            )
        elif args.command == "cnki-init":
            if args.profile:
                settings.cnki.profile = args.profile
            _print(service.cnki.initialize_profile())
        elif args.command == "zotero-probe":
            _print(service.zotero.probe())
        elif args.command == "zotero-authorize":
            print(
                "Zotero will show a confirmation dialog. Choose 'Always Allow' "
                "to support multi-step PDF imports.",
                file=sys.stderr,
            )
            _print(service.zotero.authorize_writes(require_remembered=True))
        else:  # pragma: no cover - argparse keeps this unreachable
            parser.error(f"unknown command: {args.command}")
    finally:
        service.close()
    return 0


__all__ = ["main"]
