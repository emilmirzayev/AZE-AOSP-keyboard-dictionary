#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
JAVA_BIN="${JAVA_BIN:-/opt/homebrew/opt/openjdk/bin/java}"
DICTTOOL_JAR="${DICTTOOL_JAR:-$ROOT_DIR/tools/dicttool_aosp.jar}"
SOURCE_FILE="${1:-$ROOT_DIR/az_wordlist.combined}"
OUTPUT_FILE="${2:-$ROOT_DIR/main_az.dict}"

"$JAVA_BIN" -jar "$DICTTOOL_JAR" makedict -s "$SOURCE_FILE" -d "$OUTPUT_FILE"
