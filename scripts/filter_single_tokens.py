#!/usr/bin/env python3
"""Keep only single-token dictionary entries."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter a word list down to single-token entries.")
    parser.add_argument("input", type=Path, help="Input text file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("list_of_words_single_tokens.txt"),
        help="Output text file",
    )
    args = parser.parse_args()

    lines = args.input.read_text(encoding="utf-8").splitlines()
    filtered = [line for line in lines if line.strip() and " " not in line]
    args.output.write_text("\n".join(filtered) + "\n", encoding="utf-8")
    print(f"Wrote {len(filtered)} entries to {args.output}")


if __name__ == "__main__":
    main()
