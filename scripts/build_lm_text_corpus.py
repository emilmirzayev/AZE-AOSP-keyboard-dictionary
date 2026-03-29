#!/usr/bin/env python3
"""Build cleaned train/validation text corpora from normalized JSONL documents."""

from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
import json
import re
import sqlite3
import unicodedata
from pathlib import Path


BLANK_LINES_RE = re.compile(r"\n\s*\n+")
INLINE_SPACE_RE = re.compile(r"[ \t\f\v]+")
URL_RE = re.compile(r"https?://\S+|www\.\S+")
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?…])\s+(?=[0-9A-ZƏÖÜÇŞĞİI\"'“”«])")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read normalized JSONL documents, clean and chunk them, exact-dedupe the "
            "result, and write train/validation text files."
        )
    )
    parser.add_argument("input", type=Path, help="Normalized JSONL produced by normalize_lm_corpus.py")
    parser.add_argument("--train-output", type=Path, required=True, help="Training text output")
    parser.add_argument("--valid-output", type=Path, help="Validation text output")
    parser.add_argument(
        "--valid-ratio",
        type=float,
        default=0.01,
        help="Fraction of unique chunks sent to validation output (default: 0.01)",
    )
    parser.add_argument(
        "--dedupe-db",
        type=Path,
        required=True,
        help="SQLite path used for exact dedupe across large corpora",
    )
    parser.add_argument(
        "--target-chars",
        type=int,
        default=320,
        help="Target chunk size in characters before splitting (default: 320)",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=480,
        help="Maximum chunk size in characters (default: 480)",
    )
    parser.add_argument(
        "--min-chars",
        type=int,
        default=40,
        help="Drop chunks shorter than this many characters (default: 40)",
    )
    parser.add_argument(
        "--min-letter-ratio",
        type=float,
        default=0.6,
        help="Minimum alphabetic-character ratio after cleaning (default: 0.6)",
    )
    parser.add_argument(
        "--max-documents",
        type=int,
        default=0,
        help="Optional cap on input documents for smoke tests (default: unlimited)",
    )
    return parser.parse_args()


def normalize_chunk(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\ufeff", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = URL_RE.sub(" ", text)
    text = "".join(char for char in text if char == "\n" or char >= " ")
    paragraphs = []
    for paragraph in BLANK_LINES_RE.split(text):
        paragraph = INLINE_SPACE_RE.sub(" ", paragraph.replace("\n", " ")).strip()
        if paragraph:
            paragraphs.append(paragraph)
    return "\n\n".join(paragraphs)


def letter_ratio(text: str) -> float:
    visible_chars = [char for char in text if not char.isspace()]
    if not visible_chars:
        return 0.0
    letter_count = sum(char.isalpha() for char in visible_chars)
    return letter_count / len(visible_chars)


def split_long_text(text: str, target_chars: int, max_chars: int) -> list[str]:
    paragraphs = [part.strip() for part in BLANK_LINES_RE.split(text) if part.strip()]
    chunks: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            chunks.append(paragraph)
            continue

        sentences = [piece.strip() for piece in SENTENCE_BOUNDARY_RE.split(paragraph) if piece.strip()]
        if len(sentences) <= 1:
            words = paragraph.split()
            buffer: list[str] = []
            buffer_len = 0
            for word in words:
                extra = len(word) if not buffer else len(word) + 1
                if buffer and buffer_len + extra > target_chars:
                    chunks.append(" ".join(buffer))
                    buffer = [word]
                    buffer_len = len(word)
                else:
                    buffer.append(word)
                    buffer_len += extra
            if buffer:
                chunks.append(" ".join(buffer))
            continue

        current: list[str] = []
        current_len = 0
        for sentence in sentences:
            extra = len(sentence) if not current else len(sentence) + 1
            if current and (current_len + extra > max_chars or current_len >= target_chars):
                chunks.append(" ".join(current))
                current = [sentence]
                current_len = len(sentence)
            else:
                current.append(sentence)
                current_len += extra
        if current:
            chunks.append(" ".join(current))
    return chunks


def open_dedupe_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("DROP TABLE IF EXISTS seen_hashes")
    connection.execute("CREATE TABLE seen_hashes (hash TEXT PRIMARY KEY)")
    return connection


def is_new_hash(connection: sqlite3.Connection, digest: str) -> bool:
    try:
        connection.execute("INSERT INTO seen_hashes(hash) VALUES (?)", (digest,))
    except sqlite3.IntegrityError:
        return False
    return True


def choose_split(text: str, valid_ratio: float) -> str:
    if valid_ratio <= 0:
        return "train"
    bucket = int(hashlib.sha1(text.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "valid" if bucket < valid_ratio else "train"


def main() -> None:
    args = parse_args()
    if args.valid_output and not 0 <= args.valid_ratio < 1:
        raise ValueError("--valid-ratio must be in [0, 1)")
    if not args.valid_output and args.valid_ratio:
        print("Validation ratio ignored because --valid-output was not provided")

    args.train_output.parent.mkdir(parents=True, exist_ok=True)
    if args.valid_output:
        args.valid_output.parent.mkdir(parents=True, exist_ok=True)

    stats = {
        "documents_read": 0,
        "chunks_written_train": 0,
        "chunks_written_valid": 0,
        "chunks_filtered_short": 0,
        "chunks_filtered_ratio": 0,
        "chunks_duplicate": 0,
    }

    connection = open_dedupe_db(args.dedupe_db)

    with (
        args.input.open("r", encoding="utf-8") as in_handle,
        args.train_output.open("w", encoding="utf-8") as train_handle,
        (
            args.valid_output.open("w", encoding="utf-8")
            if args.valid_output
            else nullcontext(None)
        ) as valid_handle,
    ):
        for raw_line in in_handle:
            if args.max_documents and stats["documents_read"] >= args.max_documents:
                break
            line = raw_line.strip()
            if not line:
                continue
            record = json.loads(line)
            stats["documents_read"] += 1
            text = normalize_chunk(record.get("text", ""))
            if not text:
                continue

            for chunk in split_long_text(text, args.target_chars, args.max_chars):
                chunk = chunk.strip()
                if len(chunk) < args.min_chars:
                    stats["chunks_filtered_short"] += 1
                    continue
                if letter_ratio(chunk) < args.min_letter_ratio:
                    stats["chunks_filtered_ratio"] += 1
                    continue

                digest = hashlib.sha256(chunk.encode("utf-8")).hexdigest()
                if not is_new_hash(connection, digest):
                    stats["chunks_duplicate"] += 1
                    continue

                split = choose_split(chunk, args.valid_ratio if args.valid_output else 0.0)
                if split == "valid" and valid_handle is not None:
                    valid_handle.write(chunk + "\n")
                    stats["chunks_written_valid"] += 1
                else:
                    train_handle.write(chunk + "\n")
                    stats["chunks_written_train"] += 1

            if stats["documents_read"] % 1000 == 0:
                connection.commit()

        connection.commit()
        connection.close()

    print(f"Read {stats['documents_read']} normalized documents from {args.input}")
    print(f"Wrote {stats['chunks_written_train']} training chunks to {args.train_output}")
    if args.valid_output:
        print(f"Wrote {stats['chunks_written_valid']} validation chunks to {args.valid_output}")
    print(f"Filtered {stats['chunks_filtered_short']} short chunks")
    print(f"Filtered {stats['chunks_filtered_ratio']} low-letter-ratio chunks")
    print(f"Skipped {stats['chunks_duplicate']} exact duplicate chunks")


if __name__ == "__main__":
    main()
