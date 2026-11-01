"""Command-line helpers. Usage: python -m backend.cli import-legacy [--reports-dir reports]"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .config import ROOT_DIR, load_settings
from .db import Database
from .services.legacy_import import import_legacy_reports


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m backend.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    legacy = sub.add_parser("import-legacy", help="Import analyses from the old Streamlit version")
    legacy.add_argument("--reports-dir", type=Path, default=ROOT_DIR / "reports")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    db = Database(load_settings().db_url)
    db.init()
    if args.command == "import-legacy":
        runs = import_legacy_reports(db, args.reports_dir)
        print(f"Imported {len(runs)} analyses into {db.url}")


if __name__ == "__main__":
    main()
