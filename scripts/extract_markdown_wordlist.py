#!/usr/bin/env python3
"""Extract one cleaned dictionary entry per line from markdown tables."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


SEPARATOR_RE = re.compile(r"^-+$")
SECTION_HEADER_RE = re.compile(r"^[A-ZƏÖÜÇŞĞİI][a-zəöüçşğiı]$")
SINGLE_LETTER_HEADER_RE = re.compile(r"^[A-ZƏÖÜÇŞĞİI]$")
PAGE_NUMBER_RE = re.compile(r"^\d+$")
RANGE_FOOTER_RE = re.compile(r"\s-\s")
PARENS_RE = re.compile(r"\s*\([^)]*\)")
BROKEN_PARENS_TAIL_RE = re.compile(r"\s*\([^)]*$")
BROKEN_PARENS_HEAD_RE = re.compile(r"^[^()]*\)\s*")
COMMA_QUALIFIER_RE = re.compile(r"\s*,\s+.+$")
SPACE_RE = re.compile(r"\s+")
AZ_ALPHABET = "abcçdeəfgğhxıijkqlmnoöprsştuüvyz"
AZ_ORDER = {char: index for index, char in enumerate(AZ_ALPHABET)}


def paren_balance(text: str) -> int:
    return text.count("(") - text.count(")")


def az_sort_key(text: str) -> tuple[tuple[int, int], ...]:
    lowered = "".join({"I": "ı", "İ": "i"}.get(char, char.lower()) for char in text)
    key: list[tuple[int, int]] = []
    for char in lowered:
        if char in AZ_ORDER:
            key.append((0, AZ_ORDER[char]))
        else:
            key.append((1, ord(char)))
    return tuple(key)


def is_header_cell(cell: str) -> bool:
    return bool(
        SECTION_HEADER_RE.fullmatch(cell) or SINGLE_LETTER_HEADER_RE.fullmatch(cell)
    )


def clean_cell(cell: str) -> str:
    cell = cell.strip()
    if not cell:
        return ""
    if SEPARATOR_RE.fullmatch(cell):
        return ""
    if is_header_cell(cell):
        return ""
    if PAGE_NUMBER_RE.fullmatch(cell):
        return ""
    if RANGE_FOOTER_RE.search(cell):
        return ""

    # Drop labels like "(biol.)", "(-lər)", "(tar.)".
    cell = PARENS_RE.sub("", cell)
    # If a wrapped line left behind an orphaned parenthesis fragment, drop it.
    cell = BROKEN_PARENS_TAIL_RE.sub("", cell)
    cell = BROKEN_PARENS_HEAD_RE.sub("", cell)
    # Drop qualifiers like ", armud" or ", oyun".
    cell = COMMA_QUALIFIER_RE.sub("", cell)
    cell = SPACE_RE.sub(" ", cell).strip(" ,;")

    if not cell:
        return ""
    if is_header_cell(cell):
        return ""
    return cell


def extract_entries(text: str) -> list[str]:
    seen: set[str] = set()
    entries: list[str] = []
    all_lines = text.splitlines()
    cutoff = next(
        (
            index
            for index, raw_line in enumerate(all_lines)
            if raw_line.strip() == "AZƏRBAYCAN RESPUBLİKASININ"
        ),
        len(all_lines),
    )
    lines = all_lines[:cutoff]
    index = 0
    pending_by_col: list[str] = []

    def add_entry(raw: str) -> None:
        cleaned = clean_cell(raw)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            entries.append(cleaned)

    def process_table_row(parts: list[str]) -> None:
        nonlocal pending_by_col
        if len(pending_by_col) < len(parts):
            pending_by_col.extend([""] * (len(parts) - len(pending_by_col)))

        for col, part in enumerate(parts):
            raw = part.strip()
            if not raw or SEPARATOR_RE.fullmatch(raw) or is_header_cell(raw):
                continue
            if RANGE_FOOTER_RE.search(raw) or PAGE_NUMBER_RE.fullmatch(raw):
                continue

            if pending_by_col[col]:
                pending_by_col[col] = f"{pending_by_col[col]} {raw}".strip()
                if paren_balance(pending_by_col[col]) <= 0:
                    add_entry(pending_by_col[col])
                    pending_by_col[col] = ""
                continue

            balance = paren_balance(raw)
            if balance > 0:
                pending_by_col[col] = raw
            elif balance < 0:
                continue
            else:
                add_entry(raw)

    while index < len(lines):
        raw_line = lines[index]
        line = raw_line.strip()
        if not line or PAGE_NUMBER_RE.fullmatch(line):
            index += 1
            continue
        if not line.startswith("|"):
            index += 1
            continue

        # Skip markdown table header rows and their separator rows.
        if index + 1 < len(lines):
            next_line = lines[index + 1].strip()
            if next_line.startswith("|"):
                next_parts = [part.strip() for part in next_line.strip("|").split("|")]
                if next_parts and all(not part or SEPARATOR_RE.fullmatch(part) for part in next_parts):
                    index += 2
                    continue

        parts = [part.strip() for part in line.strip("|").split("|")]
        if not parts:
            index += 1
            continue

        process_table_row(parts)
        index += 1

    for pending in pending_by_col:
        if pending:
            add_entry(pending)

    return entries


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert markdown dictionary tables into a one-entry-per-line wordlist."
    )
    parser.add_argument("input", type=Path, help="Markdown source file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("list_of_words.txt"),
        help="Output text file (default: list_of_words.txt)",
    )
    args = parser.parse_args()

    text = args.input.read_text(encoding="utf-8")
    entries = sorted(extract_entries(text), key=az_sort_key)
    args.output.write_text("\n".join(entries) + "\n", encoding="utf-8")

    print(f"Wrote {len(entries)} entries to {args.output}")


if __name__ == "__main__":
    main()
