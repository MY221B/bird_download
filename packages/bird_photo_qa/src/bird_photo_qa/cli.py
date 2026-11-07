"""CLI: ``python -m bird_photo_qa IMAGE [IMAGE ...]``"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .pipeline import evaluate_image
from .quality import detector_available


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Filter low-quality and museum-specimen bird photos.",
    )
    parser.add_argument("paths", nargs="+", type=Path, help="Image files")
    parser.add_argument("--source", default="", help="macaulay / gbif / inaturalist / …")
    parser.add_argument("--url", default="", help="Original media URL")
    parser.add_argument("--photographer", default="")
    parser.add_argument("--credit", default="")
    parser.add_argument("--no-quality", action="store_true", help="Skip detector / blur gates")
    parser.add_argument("--no-specimen", action="store_true", help="Skip museum / color-card gates")
    parser.add_argument("--no-dead", action="store_true", help="Skip iNaturalist Dead annotation gate")
    parser.add_argument(
        "--alive-or-dead",
        default="",
        help="iNaturalist Alive or Dead annotation: alive / dead",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON lines")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.no_quality and not detector_available():
        print(
            "quality filters need torch+torchvision (pip install 'bird-photo-qa[detect]'). "
            "Re-run with --no-quality to only check specimens.",
            file=sys.stderr,
        )
        return 2
    exit_code = 0
    for path in args.paths:
        if not path.is_file():
            print(f"missing: {path}", file=sys.stderr)
            exit_code = 1
            continue
        result = evaluate_image(
            path,
            source=args.source,
            source_url=args.url,
            photographer=args.photographer,
            credit=args.credit,
            quality=not args.no_quality,
            specimen=not args.no_specimen,
            dead=not args.no_dead,
            alive_or_dead=args.alive_or_dead,
        )
        if args.json:
            print(json.dumps(result.to_dict(), ensure_ascii=False))
        else:
            status = "KEEP" if result.keep else "DROP"
            extra = ",".join(result.reasons) if result.reasons else "-"
            print(f"{status}\t{extra}\t{path}")
        if not result.keep:
            exit_code = 1
    return exit_code
