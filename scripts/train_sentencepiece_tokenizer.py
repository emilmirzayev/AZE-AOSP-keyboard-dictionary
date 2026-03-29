#!/usr/bin/env python3
"""Train a SentencePiece tokenizer for Azerbaijani keyboard language modeling."""

from __future__ import annotations

import argparse
from pathlib import Path


FUTO_CORE_SYMBOLS = ["<XBU>", "<XBC>", "<XEC>"] + [
    f"<CHAR_{letter}>" for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Train a SentencePiece tokenizer with FUTO control tokens reserved. "
            "This is the tokenizer stage only; it does not train a transformer."
        )
    )
    parser.add_argument("--input", type=Path, required=True, help="Plain-text corpus, one chunk per line")
    parser.add_argument(
        "--model-prefix",
        type=Path,
        required=True,
        help="Output prefix for SentencePiece .model and .vocab files",
    )
    parser.add_argument(
        "--vocab-size",
        type=int,
        default=12000,
        help="Vocabulary size target (default: 12000)",
    )
    parser.add_argument(
        "--model-type",
        default="unigram",
        choices=["unigram", "bpe", "char", "word"],
        help="SentencePiece model type (default: unigram)",
    )
    parser.add_argument(
        "--character-coverage",
        type=float,
        default=1.0,
        help="SentencePiece character coverage (default: 1.0)",
    )
    parser.add_argument(
        "--input-sentence-size",
        type=int,
        default=0,
        help=(
            "Optional SentencePiece line sampling limit. Use 0 to read the whole corpus "
            "(default: 0)."
        ),
    )
    parser.add_argument(
        "--max-sentence-length",
        type=int,
        default=8192,
        help="Maximum line length seen by SentencePiece (default: 8192)",
    )
    parser.add_argument(
        "--extra-symbol",
        action="append",
        default=[],
        help="Additional reserved token, may be repeated",
    )
    parser.add_argument(
        "--normalization-rule-name",
        default="nmt_nfkc",
        help="SentencePiece normalization rule name (default: nmt_nfkc)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        import sentencepiece as spm
    except ImportError as exc:
        raise SystemExit(
            "sentencepiece is required for tokenizer training. Install it with "
            "'pip install sentencepiece'."
        ) from exc

    args.model_prefix.parent.mkdir(parents=True, exist_ok=True)

    user_symbols = list(dict.fromkeys(FUTO_CORE_SYMBOLS + args.extra_symbol))
    train_kwargs = {
        "input": str(args.input),
        "model_prefix": str(args.model_prefix),
        "vocab_size": args.vocab_size,
        "model_type": args.model_type,
        "character_coverage": args.character_coverage,
        "treat_whitespace_as_suffix": True,
        "split_by_whitespace": False,
        "normalization_rule_name": args.normalization_rule_name,
        "user_defined_symbols": user_symbols,
        "max_sentence_length": args.max_sentence_length,
    }
    if args.input_sentence_size:
        train_kwargs["input_sentence_size"] = args.input_sentence_size
        train_kwargs["shuffle_input_sentence"] = True

    spm.SentencePieceTrainer.Train(**train_kwargs)

    print(f"Wrote tokenizer model to {args.model_prefix}.model")
    print(f"Wrote tokenizer vocab to {args.model_prefix}.vocab")
    print(f"Reserved {len(user_symbols)} symbols")


if __name__ == "__main__":
    main()
