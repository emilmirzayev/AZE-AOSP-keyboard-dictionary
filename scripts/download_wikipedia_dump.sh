#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
OUTPUT_FILE="${1:-$ROOT_DIR/data/raw/azwiki-latest-pages-articles.xml.bz2}"
WIKI_URL="https://dumps.wikimedia.org/azwiki/latest/azwiki-latest-pages-articles.xml.bz2"

mkdir -p "$(dirname "$OUTPUT_FILE")"
curl --fail --location --output "$OUTPUT_FILE" "$WIKI_URL"

printf 'Downloaded %s\n' "$OUTPUT_FILE"
