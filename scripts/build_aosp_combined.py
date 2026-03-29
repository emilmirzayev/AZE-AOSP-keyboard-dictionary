#!/usr/bin/env python3
"""Build an AOSP/LatinIME .combined dictionary source from a word list."""

from __future__ import annotations

import argparse
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a one-word-per-line list into an AOSP .combined file."
    )
    parser.add_argument("input", type=Path, help="Input word list")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("az_wordlist.combined"),
        help="Output .combined file",
    )
    parser.add_argument(
        "--locale",
        default="az",
        help="Locale to embed in the dictionary header (default: az)",
    )
    parser.add_argument(
        "--dictionary-id",
        default="main:az",
        help="Dictionary id to embed in the header (default: main:az)",
    )
    parser.add_argument(
        "--description",
        default=(
            "Azerbaijani wordlist converted from "
            "Azərbaycan dilinin orfoqrafiya lüğəti"
        ),
        help="Description to embed in the dictionary header",
    )
    parser.add_argument(
        "--frequency",
        type=int,
        default=180,
        help="Default unigram frequency for each word (0-255, default: 180)",
    )
    parser.add_argument(
        "--version",
        type=int,
        default=1,
        help="Dictionary version in the header (default: 1)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not 0 <= args.frequency <= 255:
        raise SystemExit("--frequency must be between 0 and 255")

    words = [
        line.strip()
        for line in args.input.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    header = (
        f"dictionary={args.dictionary_id},"
        f"locale={args.locale},"
        f"description={args.description},"
        f"date={int(time.time())},"
        f"version={args.version}"
    )

    body = [f"word={word},f={args.frequency}" for word in words]
    args.output.write_text("\n".join([header, *body]) + "\n", encoding="utf-8")
    print(f"Wrote {len(words)} entries to {args.output}")


if __name__ == "__main__":
    main()
