#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
AFF_FILE="${1:-$ROOT_DIR/data/raw/az.aff}"
DIC_FILE="${2:-$ROOT_DIR/data/raw/az.dic}"
BASE_URL="https://raw.githubusercontent.com/mozillaz/spellchecker/master/dictionaries"

mkdir -p "$(dirname "$AFF_FILE")"
curl --fail --location --output "$AFF_FILE" "$BASE_URL/az.aff"
curl --fail --location --output "$DIC_FILE" "$BASE_URL/az.dic"

printf 'Downloaded %s\n' "$AFF_FILE"
printf 'Downloaded %s\n' "$DIC_FILE"
