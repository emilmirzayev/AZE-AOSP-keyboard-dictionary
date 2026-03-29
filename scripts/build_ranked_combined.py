#!/usr/bin/env python3
"""Build a weighted AOSP/FUTO .combined dictionary from SQLite counts."""

from __future__ import annotations

import argparse
import math
import sqlite3
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build an AOSP/FUTO .combined dictionary from filtered SQLite "
            "unigram and bigram counts."
        )
    )
    parser.add_argument("--db", type=Path, required=True, help="SQLite counts database")
    parser.add_argument(
        "--valid-forms",
        type=Path,
        required=True,
        help="Expanded allowlist used to accept corpus words",
    )
    parser.add_argument(
        "--backfill-forms",
        type=Path,
        help="Compact fallback list for unseen entries to include at low frequency",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("artifacts/az_ranked.combined"),
        help="Output .combined file",
    )
    parser.add_argument("--locale", default="az", help="Locale for dictionary header")
    parser.add_argument(
        "--dictionary-id",
        default="main:az",
        help="Dictionary id for header (default: main:az)",
    )
    parser.add_argument(
        "--description",
        default="Azerbaijani dictionary built from azwiki and Mozilla Hunspell",
        help="Description embedded in the dictionary header",
    )
    parser.add_argument(
        "--version",
        type=int,
        default=18,
        help="Dictionary header version (default: 18)",
    )
    parser.add_argument(
        "--top-bigrams",
        type=int,
        default=8,
        help="Maximum number of bigrams per head word (default: 8)",
    )
    parser.add_argument(
        "--min-bigram-count",
        type=int,
        default=2,
        help="Minimum bigram count to include (default: 2)",
    )
    parser.add_argument(
        "--seen-min-frequency",
        type=int,
        default=32,
        help="Minimum f= weight for words seen in corpus (default: 32)",
    )
    parser.add_argument(
        "--unseen-frequency",
        type=int,
        default=6,
        help="Fallback f= weight for backfill entries unseen in corpus (default: 6)",
    )
    parser.add_argument(
        "--bigram-min-frequency",
        type=int,
        default=48,
        help="Minimum f= weight for retained bigrams (default: 48)",
    )
    return parser.parse_args()


def load_word_set(path: Path | None) -> set[str]:
    if not path:
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def scale_log(value: int, floor: int, ceiling: int, low: int, high: int) -> int:
    if value <= 0:
        return low
    if ceiling <= floor:
        return high
    position = (math.log(value) - math.log(floor)) / (math.log(ceiling) - math.log(floor))
    score = low + (high - low) * position
    return max(low, min(high, int(round(score))))


def load_seen_counts(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    return list(
        conn.execute(
            "SELECT word, count FROM unigram_counts ORDER BY count DESC, word ASC"
        )
    )


def load_top_bigrams(
    conn: sqlite3.Connection,
    included_words: set[str],
    top_n: int,
    min_count: int,
) -> dict[str, list[tuple[str, int]]]:
    buckets: dict[str, list[tuple[str, int]]] = {}
    query = (
        "SELECT w1, w2, count FROM bigram_counts WHERE count >= ? "
        "ORDER BY w1 ASC, count DESC, w2 ASC"
    )
    for w1, w2, count in conn.execute(query, (min_count,)):
        if w1 not in included_words or w2 not in included_words:
            continue
        bucket = buckets.setdefault(w1, [])
        if len(bucket) < top_n:
            bucket.append((w2, count))
    return buckets


def main() -> None:
    args = parse_args()
    valid_forms = load_word_set(args.valid_forms)
    backfill_forms = load_word_set(args.backfill_forms) if args.backfill_forms else valid_forms
    conn = sqlite3.connect(args.db)

    seen_rows = load_seen_counts(conn)
    seen_counts = {word: count for word, count in seen_rows if word in valid_forms}
    ordered_words = [word for word, _ in seen_rows if word in valid_forms]

    unseen_words = sorted(backfill_forms - set(seen_counts))
    ordered_words.extend(unseen_words)

    included_words = set(ordered_words)
    top_bigrams = load_top_bigrams(
        conn,
        included_words=included_words,
        top_n=args.top_bigrams,
        min_count=args.min_bigram_count,
    )
    conn.close()

    seen_values = list(seen_counts.values())
    min_seen = min(seen_values) if seen_values else 1
    max_seen = max(seen_values) if seen_values else 1

    header = (
        f"dictionary={args.dictionary_id},"
        f"locale={args.locale},"
        f"description={args.description},"
        f"date={int(time.time())},"
        f"version={args.version}"
    )

    word_frequencies: dict[str, int] = {}
    for word in ordered_words:
        count = seen_counts.get(word, 0)
        if count:
            word_frequencies[word] = scale_log(
                count,
                floor=min_seen,
                ceiling=max_seen,
                low=args.seen_min_frequency,
                high=255,
            )
        else:
            word_frequencies[word] = args.unseen_frequency

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        handle.write(header + "\n")
        for word in ordered_words:
            frequency = word_frequencies[word]
            handle.write(f" word={word},f={frequency}\n")

            followers = top_bigrams.get(word, [])
            if not followers:
                continue

            follower_counts = [bigram_count for _, bigram_count in followers]
            min_bigram = min(follower_counts)
            max_bigram = max(follower_counts)
            for follower, bigram_count in followers:
                scaled_bigram = scale_log(
                    bigram_count,
                    floor=min_bigram,
                    ceiling=max_bigram,
                    low=args.bigram_min_frequency,
                    high=255,
                )
                bigram_frequency = max(scaled_bigram, word_frequencies.get(follower, args.unseen_frequency))
                handle.write(f"  bigram={follower},f={bigram_frequency}\n")

    print(f"Seen corpus words: {len(seen_counts):,}")
    print(f"Backfill-only entries: {len(unseen_words):,}")
    print(f"Total dictionary entries: {len(ordered_words):,}")
    print(f"Words with bigrams: {len(top_bigrams):,}")
    print(f"Wrote ranked combined dictionary to {args.output}")


if __name__ == "__main__":
    main()
