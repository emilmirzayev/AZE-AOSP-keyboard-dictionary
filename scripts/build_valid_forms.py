#!/usr/bin/env python3
"""Build Azerbaijani form lists from orthography and Hunspell data."""

from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

WORD_RE = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*\Z", re.UNICODE)


@dataclass(frozen=True)
class AffixRule:
    strip: str
    add: str
    condition: str
    continuation_flags: tuple[str, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build allowlist and backfill word lists from the orthography source "
            "and Azerbaijani Hunspell files."
        )
    )
    parser.add_argument("--orthography", type=Path, required=True, help="Orthography list")
    parser.add_argument("--dic", type=Path, required=True, help="Hunspell .dic file")
    parser.add_argument("--aff", type=Path, required=True, help="Hunspell .aff file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("data/intermediate/valid_forms.txt"),
        help="Expanded allowlist output used for corpus filtering",
    )
    parser.add_argument(
        "--hunspell-output",
        type=Path,
        default=Path("data/intermediate/hunspell_forms.txt"),
        help="Expanded Hunspell-only form list",
    )
    parser.add_argument(
        "--hunspell-stems-output",
        type=Path,
        default=Path("data/intermediate/hunspell_stems.txt"),
        help="Exact Hunspell stem entries without generated suffix forms",
    )
    parser.add_argument(
        "--backfill-output",
        type=Path,
        default=Path("data/intermediate/backfill_forms.txt"),
        help="Compact fallback list used for unseen dictionary entries",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=2,
        help="Maximum continuation-depth for Hunspell suffix expansion (default: 2)",
    )
    return parser.parse_args()


def split_flags(raw: str) -> tuple[str, ...]:
    raw = raw.strip()
    if not raw:
        return ()

    flags: list[str] = []
    index = 0
    while index < len(raw):
        remaining = len(raw) - index
        step = 2 if remaining >= 2 else 1
        flags.append(raw[index : index + step])
        index += step
    return tuple(flag for flag in flags if flag)


def is_word(word: str) -> bool:
    return bool(word) and len(word) <= 48 and bool(WORD_RE.fullmatch(word))


def parse_aff(path: Path) -> tuple[dict[str, list[AffixRule]], set[str]]:
    rules_by_flag: dict[str, list[AffixRule]] = defaultdict(list)
    defined_flags: set[str] = set()

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "#" in line:
            line = line.split("#", 1)[0].rstrip()
        if not line:
            continue

        parts = line.split()
        if not parts or parts[0] != "SFX":
            continue

        if len(parts) == 4 and parts[2] in {"Y", "N"} and parts[3].isdigit():
            defined_flags.add(parts[1])
            continue

        if len(parts) < 4:
            continue

        flag = parts[1]
        defined_flags.add(flag)

        strip_field = parts[2]
        add_field = parts[3]
        condition = parts[4] if len(parts) > 4 else "."

        if len(parts) == 4 and add_field.endswith(".") and add_field not in {"0.", "."}:
            add_field = add_field[:-1]
            condition = "."

        add_value, _, continuation = add_field.partition("/")
        strip = "" if strip_field == "0" else strip_field
        add = "" if add_value == "0" else add_value
        rules_by_flag[flag].append(
            AffixRule(
                strip=strip,
                add=add,
                condition=condition,
                continuation_flags=split_flags(continuation),
            )
        )

    return dict(rules_by_flag), defined_flags


def parse_dic_entry(line: str) -> tuple[str, tuple[str, ...]]:
    token = line.split()[0]
    stem, _, raw_flags = token.partition("/")
    return stem.strip().lower(), split_flags(raw_flags)


def condition_matches(word: str, condition: str) -> bool:
    if condition in {"", "."}:
        return True
    return re.search(condition + r"$", word) is not None


def apply_rule(word: str, rule: AffixRule) -> str | None:
    if rule.strip and not word.endswith(rule.strip):
        return None
    if not condition_matches(word, rule.condition):
        return None
    base = word[: -len(rule.strip)] if rule.strip else word
    return base + rule.add


def expand_forms(
    stem: str,
    flags: tuple[str, ...],
    rules_by_flag: dict[str, list[AffixRule]],
    max_depth: int,
) -> set[str]:
    forms = {stem}
    initial_flags = tuple(flag for flag in flags if flag in rules_by_flag)
    if not initial_flags:
        return forms

    queue: list[tuple[str, tuple[str, ...], int]] = [(stem, initial_flags, 0)]
    seen_states = {(stem, initial_flags, 0)}

    while queue:
        word, active_flags, depth = queue.pop()
        if depth >= max_depth:
            continue

        for flag in active_flags:
            for rule in rules_by_flag.get(flag, ()):  # pragma: no branch
                candidate = apply_rule(word, rule)
                if not candidate or not is_word(candidate):
                    continue
                forms.add(candidate)

                next_flags = tuple(
                    next_flag
                    for next_flag in rule.continuation_flags
                    if next_flag in rules_by_flag
                )
                if not next_flags:
                    continue

                state = (candidate, next_flags, depth + 1)
                if state in seen_states:
                    continue
                seen_states.add(state)
                queue.append(state)

    return forms


def load_word_list(path: Path) -> set[str]:
    return {
        line.strip().lower()
        for line in path.read_text(encoding="utf-8").splitlines()
        if is_word(line.strip().lower())
    }


def write_words(path: Path, words: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(sorted(words)) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()

    orthography_words = load_word_list(args.orthography)
    rules_by_flag, defined_flags = parse_aff(args.aff)

    hunspell_stems: set[str] = set()
    hunspell_forms: set[str] = set()
    seen_flags: Counter[str] = Counter()
    expanded_entries = 0

    lines = args.dic.read_text(encoding="utf-8").splitlines()
    for raw_line in lines[1:]:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        stem, flags = parse_dic_entry(line)
        if not is_word(stem):
            continue

        hunspell_stems.add(stem)
        hunspell_forms.add(stem)
        seen_flags.update(flags)

        expanded = expand_forms(stem, flags, rules_by_flag, args.max_depth)
        if len(expanded) > 1:
            expanded_entries += 1
        hunspell_forms.update(expanded)

    valid_forms = orthography_words | hunspell_forms
    backfill_forms = orthography_words | hunspell_stems
    undefined_flags = sorted(flag for flag in seen_flags if flag not in defined_flags)

    write_words(args.hunspell_stems_output, hunspell_stems)
    write_words(args.hunspell_output, hunspell_forms)
    write_words(args.backfill_output, backfill_forms)
    write_words(args.output, valid_forms)

    print(f"Orthography words: {len(orthography_words):,}")
    print(f"Hunspell stems: {len(hunspell_stems):,}")
    print(f"Hunspell forms: {len(hunspell_forms):,}")
    print(f"Expanded allowlist: {len(valid_forms):,}")
    print(f"Compact backfill forms: {len(backfill_forms):,}")
    print(f"Expanded Hunspell entries: {expanded_entries:,}")
    if undefined_flags:
        preview = ", ".join(undefined_flags[:12])
        extra = "" if len(undefined_flags) <= 12 else f" ... (+{len(undefined_flags) - 12} more)"
        print(f"Flags without affix rules kept as exact forms only: {preview}{extra}")


if __name__ == "__main__":
    main()
