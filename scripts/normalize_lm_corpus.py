#!/usr/bin/env python3
"""Normalize heterogeneous language-model corpora into a JSONL stream."""

from __future__ import annotations

import argparse
import csv
import glob
import gzip
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Iterator


WHITESPACE_RE = re.compile(r"[ \t\f\v]+")
BLANK_LINES_RE = re.compile(r"\n{3,}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read heterogeneous text datasets from a manifest and normalize them "
            "into a JSONL stream with one document per line."
        )
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Path to a corpus manifest JSON file",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output JSONL path",
    )
    parser.add_argument(
        "--allow-missing-paths",
        action="store_true",
        help="Skip manifest path patterns that do not match any local files",
    )
    parser.add_argument(
        "--max-records-per-source",
        type=int,
        default=0,
        help="Optional per-source cap for smoke tests (default: unlimited)",
    )
    return parser.parse_args()


def load_manifest(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("Manifest must contain a non-empty 'sources' list")
    return sources


def resolve_patterns(
    manifest_path: Path, patterns: Iterable[str], allow_missing: bool
) -> list[Path]:
    base_dir = manifest_path.parent
    resolved: list[Path] = []
    for pattern in patterns:
        pattern_path = Path(pattern)
        full_pattern = pattern_path if pattern_path.is_absolute() else base_dir / pattern_path
        matches = [Path(match) for match in sorted(glob.glob(str(full_pattern), recursive=True))]
        if not matches and not allow_missing:
            raise FileNotFoundError(f"No files matched pattern: {pattern}")
        resolved.extend(match.resolve() for match in matches)
    return resolved


def detect_format(source: dict[str, Any], path: Path) -> str:
    explicit = source.get("format", "auto")
    if explicit != "auto":
        return explicit

    suffixes = path.suffixes
    if suffixes[-2:] == [".jsonl", ".gz"]:
        return "jsonl.gz"
    if suffixes[-2:] == [".json", ".gz"]:
        return "json.gz"
    if suffixes[-2:] == [".txt", ".gz"]:
        return "txt.gz"
    if path.suffix == ".jsonl":
        return "jsonl"
    if path.suffix == ".json":
        return "json"
    if path.suffix == ".txt":
        return "txt"
    if path.suffix == ".csv":
        return "csv"
    if path.suffix == ".parquet":
        return "parquet"
    raise ValueError(f"Could not infer format for {path}")


def open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def get_nested_value(record: Any, field_path: str) -> Any:
    current = record
    for part in field_path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (TypeError, ValueError, IndexError) as exc:
                raise KeyError(field_path) from exc
        else:
            raise KeyError(field_path)
    return current


def flatten_text_parts(value: Any) -> Iterator[str]:
    if value is None:
        return
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, (int, float)):
        yield str(value)
        return
    if isinstance(value, list):
        for item in value:
            yield from flatten_text_parts(item)
        return
    raise TypeError(f"Unsupported text field value: {type(value).__name__}")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\ufeff", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(char for char in text if char == "\n" or char >= " ")
    text = WHITESPACE_RE.sub(" ", text)
    text = BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


def build_document_text(record: Any, source: dict[str, Any]) -> str:
    text_fields = source.get("text_fields", [])
    joiner = source.get("field_joiner", "\n\n")
    if text_fields:
        parts: list[str] = []
        for field_path in text_fields:
            try:
                raw_value = get_nested_value(record, field_path)
            except KeyError:
                raw_value = None
            field_parts = [normalize_text(part) for part in flatten_text_parts(raw_value)]
            field_parts = [part for part in field_parts if part]
            if field_parts:
                parts.append(joiner.join(field_parts))
        return joiner.join(part for part in parts if part)
    if isinstance(record, str):
        return normalize_text(record)
    raise ValueError("Source record needs 'text_fields' unless the record is a raw string")


def extract_record_id(record: Any, source: dict[str, Any], fallback: str) -> str:
    record_id_field = source.get("record_id_field")
    if record_id_field and isinstance(record, dict):
        try:
            value = get_nested_value(record, record_id_field)
        except KeyError:
            value = None
        if value not in (None, ""):
            return str(value)
    return fallback


def iter_json_records(path: Path, records_path: str | None) -> Iterator[Any]:
    with open_text(path) as handle:
        payload = json.load(handle)
    if records_path:
        payload = get_nested_value(payload, records_path)
    if isinstance(payload, list):
        yield from payload
        return
    if isinstance(payload, dict):
        yield payload
        return
    raise ValueError(f"Unsupported JSON root in {path}")


def iter_jsonl_records(path: Path) -> Iterator[Any]:
    with open_text(path) as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSONL") from exc


def iter_csv_records(path: Path) -> Iterator[dict[str, str]]:
    with open_text(path) as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            yield dict(row)


def iter_parquet_records(path: Path, batch_size: int) -> Iterator[dict[str, Any]]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "Parquet support requires pyarrow. Install it with 'pip install pyarrow'."
        ) from exc

    parquet_file = pq.ParquetFile(path)
    for batch in parquet_file.iter_batches(batch_size=batch_size):
        frame = batch.to_pylist()
        for row in frame:
            yield row


def iter_text_records(path: Path, source: dict[str, Any]) -> Iterator[str]:
    mode = source.get("text_mode", "document")
    with open_text(path) as handle:
        if mode == "document":
            text = handle.read()
            if text.strip():
                yield text
            return
        if mode == "lines":
            for raw_line in handle:
                line = raw_line.strip()
                if line:
                    yield line
            return
        if mode == "paragraphs":
            buffer: list[str] = []
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    if buffer:
                        yield "\n".join(buffer)
                        buffer.clear()
                    continue
                buffer.append(line)
            if buffer:
                yield "\n".join(buffer)
            return
    raise ValueError(f"Unsupported text_mode '{mode}' for {path}")


def iter_source_records(path: Path, source: dict[str, Any]) -> Iterator[Any]:
    fmt = detect_format(source, path)
    if fmt in {"jsonl", "jsonl.gz"}:
        yield from iter_jsonl_records(path)
        return
    if fmt in {"json", "json.gz"}:
        yield from iter_json_records(path, source.get("records_path"))
        return
    if fmt == "csv":
        yield from iter_csv_records(path)
        return
    if fmt == "parquet":
        yield from iter_parquet_records(path, int(source.get("parquet_batch_size", 1000)))
        return
    if fmt in {"txt", "txt.gz"}:
        yield from iter_text_records(path, source)
        return
    raise ValueError(f"Unsupported format '{fmt}'")


def main() -> None:
    args = parse_args()
    sources = load_manifest(args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    documents_written = 0
    source_totals: dict[str, int] = {}

    with args.output.open("w", encoding="utf-8") as out_handle:
        for source in sources:
            name = source.get("name")
            if not name:
                raise ValueError("Each source needs a 'name'")

            raw_patterns = source.get("paths") or ([source["path"]] if "path" in source else None)
            if not raw_patterns:
                raise ValueError(f"Source '{name}' needs 'path' or 'paths'")

            paths = resolve_patterns(args.manifest, raw_patterns, args.allow_missing_paths)
            source_count = 0
            for path in paths:
                for record_index, record in enumerate(iter_source_records(path, source), start=1):
                    if args.max_records_per_source and source_count >= args.max_records_per_source:
                        break
                    text = build_document_text(record, source)
                    if not text:
                        continue
                    payload = {
                        "source": name,
                        "source_path": str(path),
                        "record_id": extract_record_id(
                            record, source, fallback=f"{path.name}:{record_index}"
                        ),
                        "text": text,
                    }
                    out_handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
                    source_count += 1
                    documents_written += 1
                if args.max_records_per_source and source_count >= args.max_records_per_source:
                    break
            source_totals[name] = source_count

    print(f"Wrote {documents_written} normalized documents to {args.output}")
    for name, count in sorted(source_totals.items()):
        print(f"  {name}: {count}")


if __name__ == "__main__":
    main()
