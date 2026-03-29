#!/usr/bin/env python3
'''Stream the Azerbaijani Wikipedia dump into filtered unigram and bigram counts.'''

from __future__ import annotations

import argparse
import bz2
import html
import re
import sqlite3
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

TOKEN_RE = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*", re.UNICODE)
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
REF_BLOCK_RE = re.compile(r"<ref\b[^>/]*?>.*?</ref>", re.DOTALL | re.IGNORECASE)
REF_SELF_RE = re.compile(r"<ref\b[^>]*/\s*>", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
EXTERNAL_LINK_RE = re.compile(
    r"\[(?:https?|ftp)://[^\s\]]+(?:\s+([^\]]+))?\]",
    re.IGNORECASE,
)
INTERNAL_LINK_RE = re.compile(r"\[\[([^\[\]]+)\]\]")
WHITESPACE_RE = re.compile(r"\s+")
SENTENCE_SPLIT_RE = re.compile(r"[.!?;:\n]+")
DROP_NAMESPACES = {
    "category",
    "fayl",
    "file",
    "help",
    "image",
    "istifadəçi",
    "kateqoriya",
    "kömək",
    "media",
    "mediawiki",
    "portal",
    "special",
    "template",
    "vikipediya",
    "wikipedia",
    "xüsusi",
    "şablon",
    "şəkil",
}
REDIRECT_PREFIXES = (
    "#redirect",
    "#yönləndir",
    "#istiqamətləndirmə",
    "#i̇stiqamətləndirmə",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Stream a Wikimedia XML .bz2 dump and count allowlisted Azerbaijani "
            "unigrams and bigrams into SQLite."
        )
    )
    parser.add_argument("--dump", type=Path, required=True, help="Wikipedia dump (.xml.bz2)")
    parser.add_argument(
        "--allowlist",
        type=Path,
        required=True,
        help="One-word-per-line valid form list used to filter tokens",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/intermediate/wiki_counts.sqlite"),
        help="SQLite output database",
    )
    parser.add_argument(
        "--flush-pages",
        type=int,
        default=500,
        help="Flush batch counters to SQLite every N article pages (default: 500)",
    )
    parser.add_argument(
        "--max-bigram-batch",
        type=int,
        default=200000,
        help="Flush early if the in-memory bigram batch exceeds this many keys",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=1000,
        help="Print progress every N article pages (default: 1000)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="Optional article-page limit for smoke tests (default: 0 = no limit)",
    )
    return parser.parse_args()


def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFC", text.lower().replace("’", "'"))


def tag_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def is_redirect_text(text: str) -> bool:
    lowered = normalize_text(text).lstrip()
    return any(lowered.startswith(prefix) for prefix in REDIRECT_PREFIXES)


def strip_balanced(text: str, opener: str, closer: str) -> str:
    pieces: list[str] = []
    depth = 0
    index = 0
    while index < len(text):
        if text.startswith(opener, index):
            depth += 1
            index += len(opener)
            continue
        if depth and text.startswith(closer, index):
            depth -= 1
            index += len(closer)
            continue
        if depth == 0:
            pieces.append(text[index])
        index += 1
    return "".join(pieces)


def replace_external_link(match: re.Match[str]) -> str:
    label = match.group(1)
    return f" {label} " if label else " "


def replace_internal_link(match: re.Match[str]) -> str:
    inner = match.group(1).strip()
    if not inner:
        return " "

    target = inner.split("|", 1)[0].strip()
    if ":" in target:
        prefix = target.split(":", 1)[0].strip().lower()
        if prefix in DROP_NAMESPACES:
            return " "

    visible = inner.rsplit("|", 1)[-1].strip()
    if not visible:
        visible = target
    visible = visible.split("#", 1)[0].replace("_", " ")
    return f" {visible} " if visible else " "


def clean_wikitext(text: str) -> str:
    text = html.unescape(text)
    text = COMMENT_RE.sub(" ", text)
    text = REF_BLOCK_RE.sub(" ", text)
    text = REF_SELF_RE.sub(" ", text)
    text = strip_balanced(text, "{{", "}}")
    text = strip_balanced(text, "{|", "|}")
    text = EXTERNAL_LINK_RE.sub(replace_external_link, text)
    text = INTERNAL_LINK_RE.sub(replace_internal_link, text)
    text = TAG_RE.sub(" ", text)
    text = text.replace("'''", " ").replace("''", " ")
    text = text.replace("[[", " ").replace("]]", " ")
    text = text.replace("__TOC__", " ").replace("__NOTOC__", " ")
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip()


def load_allowlist(path: Path) -> set[str]:
    return {
        normalize_text(line.strip())
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def is_candidate_token(token: str) -> bool:
    return 1 <= len(token) <= 48


def iter_sentence_tokens(text: str, allowlist: set[str]) -> list[list[str]]:
    cleaned = clean_wikitext(text)
    if not cleaned:
        return []

    sentences: list[list[str]] = []
    for chunk in SENTENCE_SPLIT_RE.split(cleaned):
        normalized = normalize_text(chunk)
        tokens = [
            match.group(0)
            for match in TOKEN_RE.finditer(normalized)
            if is_candidate_token(match.group(0)) and match.group(0) in allowlist
        ]
        if tokens:
            sentences.append(tokens)
    return sentences


def create_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-100000")
    conn.execute(
        "CREATE TABLE unigram_counts (word TEXT PRIMARY KEY, count INTEGER NOT NULL) WITHOUT ROWID"
    )
    conn.execute(
        "CREATE TABLE bigram_counts (w1 TEXT NOT NULL, w2 TEXT NOT NULL, count INTEGER NOT NULL, PRIMARY KEY (w1, w2)) WITHOUT ROWID"
    )
    conn.execute(
        "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID"
    )
    return conn


def flush_batch(
    conn: sqlite3.Connection,
    unigrams: Counter[str],
    bigrams: Counter[tuple[str, str]],
) -> None:
    if not unigrams and not bigrams:
        return

    with conn:
        conn.executemany(
            "INSERT INTO unigram_counts(word, count) VALUES(?, ?) "
            "ON CONFLICT(word) DO UPDATE SET count = count + excluded.count",
            unigrams.items(),
        )
        conn.executemany(
            "INSERT INTO bigram_counts(w1, w2, count) VALUES(?, ?, ?) "
            "ON CONFLICT(w1, w2) DO UPDATE SET count = count + excluded.count",
            ((w1, w2, count) for (w1, w2), count in bigrams.items()),
        )

    unigrams.clear()
    bigrams.clear()


def main() -> None:
    args = parse_args()
    allowlist = load_allowlist(args.allowlist)
    conn = create_database(args.db)

    batch_unigrams: Counter[str] = Counter()
    batch_bigrams: Counter[tuple[str, str]] = Counter()
    article_pages = 0
    articles_with_tokens = 0
    kept_tokens = 0
    kept_bigrams = 0

    context = ET.iterparse(bz2.open(args.dump, "rb"), events=("start", "end"))
    _, root = next(context)

    for event, elem in context:
        if event != "end" or tag_name(elem.tag) != "page":
            continue

        ns = elem.findtext("./{*}ns")
        if ns != "0":
            root.clear()
            continue

        if args.max_pages and article_pages >= args.max_pages:
            root.clear()
            break

        article_pages += 1

        is_redirect = elem.find("./{*}redirect") is not None
        text = elem.findtext("./{*}revision/{*}text") or ""

        if not is_redirect and not is_redirect_text(text):
            page_token_total = 0
            for tokens in iter_sentence_tokens(text, allowlist):
                batch_unigrams.update(tokens)
                bigram_pairs = list(zip(tokens, tokens[1:]))
                if bigram_pairs:
                    batch_bigrams.update(bigram_pairs)
                    kept_bigrams += len(bigram_pairs)
                kept_tokens += len(tokens)
                page_token_total += len(tokens)
            if page_token_total:
                articles_with_tokens += 1

        if (
            article_pages % args.flush_pages == 0
            or len(batch_bigrams) >= args.max_bigram_batch
        ):
            flush_batch(conn, batch_unigrams, batch_bigrams)

        if article_pages % args.progress_every == 0:
            print(
                "Processed "
                f"{article_pages:,} article pages | "
                f"kept tokens: {kept_tokens:,} | "
                f"articles with tokens: {articles_with_tokens:,}"
            )

        root.clear()

    flush_batch(conn, batch_unigrams, batch_bigrams)

    metadata = {
        "allowlist_size": str(len(allowlist)),
        "article_pages": str(article_pages),
        "articles_with_tokens": str(articles_with_tokens),
        "kept_tokens": str(kept_tokens),
        "kept_bigrams": str(kept_bigrams),
    }
    with conn:
        conn.executemany(
            "INSERT INTO metadata(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            metadata.items(),
        )

    distinct_unigrams = conn.execute("SELECT COUNT(*) FROM unigram_counts").fetchone()[0]
    distinct_bigrams = conn.execute("SELECT COUNT(*) FROM bigram_counts").fetchone()[0]
    conn.close()

    print(f"Allowlist size: {len(allowlist):,}")
    print(f"Article pages processed: {article_pages:,}")
    print(f"Articles with kept tokens: {articles_with_tokens:,}")
    print(f"Kept tokens: {kept_tokens:,}")
    print(f"Distinct unigrams: {distinct_unigrams:,}")
    print(f"Distinct bigrams: {distinct_bigrams:,}")
    print(f"SQLite counts database: {args.db}")


if __name__ == "__main__":
    main()
