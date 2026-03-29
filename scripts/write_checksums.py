#!/usr/bin/env python3
"""Write SHA256 checksums for one or more files."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Write SHA256 checksums for files.")
    parser.add_argument("files", nargs="+", type=Path, help="Files to hash")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("manifests/checksums.local.txt"),
        help="Output checksum manifest",
    )
    args = parser.parse_args()

    lines = []
    for path in args.files:
        if not path.exists() or not path.is_file():
            raise SystemExit(f"Not a readable file: {path}")
        lines.append(f"{sha256(path)}  {path}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(lines)} checksums to {args.output}")


if __name__ == "__main__":
    main()
