# Azerbaijani FUTO Keyboard Dictionary

Reproducible build pipeline for an Azerbaijani dictionary and next-word prediction model for FUTO Keyboard / AOSP-style dictionaries.

This repo builds two kinds of outputs:

- a human-readable `.combined` source dictionary
- a compiled binary `.dict` that can be imported into FUTO Keyboard

## What This Repo Does

The pipeline combines three sources:

- an orthography-derived word list for trusted spellings
- Azerbaijani Hunspell data for stems and many inflected forms
- the Azerbaijani Wikipedia dump for real unigram frequencies and next-word bigrams

Important design choice:

- the large expanded Hunspell + orthography list is used as an allowlist for filtering Wikipedia text
- the final dictionary does **not** include every generated form blindly
- instead, the final dictionary includes:
  - words actually seen in the Wikipedia corpus
  - a smaller unseen backfill list from orthography + exact Hunspell stems

This keeps the final keyboard dictionary practical while still recognizing many real Azerbaijani forms.

## Repo Layout

- `scripts/`: build and extraction scripts
- `data/raw/`: local raw inputs, not meant to be committed
- `data/intermediate/`: temporary and generated working files
- `artifacts/`: final outputs that may be published
- `manifests/`: source manifests, checksums, and reproducibility metadata
- `docs/`: technical notes

## Required Local Inputs

Put these files in `data/raw/`.

### 1. Azerbaijani Wikipedia dump

Expected filename:

- `azwiki-latest-pages-articles.xml.bz2`

Source:

- `https://dumps.wikimedia.org/azwiki/latest/azwiki-latest-pages-articles.xml.bz2`

Notes:

- keep the file compressed as `.bz2`
- the pipeline stream-reads it directly and does not need the 1.6 GB XML unpacked to disk
- this file is used for unigram frequencies and bigram next-word counts

### 2. Azerbaijani Hunspell files

Expected filenames:

- `az.aff`
- `az.dic`

Source repository:

- `https://github.com/mozillaz/spellchecker/tree/master/dictionaries`

Notes:

- these files provide stems and suffix rules
- `az.dic` is not a frequency corpus
- `az.aff` does not cover every flag seen in `az.dic`, so undefined flags are kept as exact forms only

### 3. Orthography source markdown

Expected filename:

- `list_of_words.md`

Notes:

- this is the markdown-converted orthography source used for the baseline extraction step
- it is kept local and is not required to be committed

## Running From Scratch

### 1. Clone the repo

```sh
git clone <your-repo-url>
cd AZE-AOSP-keyboard-dictionary
```

### 2. Install prerequisites

You need:

- `python3`
- `make`
- `curl`
- `java`

On macOS with Homebrew, one working setup is:

```sh
brew install openjdk
```

If needed, point the build at your Java binary:

```sh
export JAVA_BIN=/opt/homebrew/opt/openjdk/bin/java
```

### 3. Get the public input files

You can download the public sources either manually or with `make`.

Manual download:

- Wikipedia dump: `https://dumps.wikimedia.org/azwiki/latest/azwiki-latest-pages-articles.xml.bz2`
- Hunspell files: `https://github.com/mozillaz/spellchecker/tree/master/dictionaries`

Helper targets:

```sh
make fetch-public-data
```

Or individually:

```sh
make fetch-wiki
make fetch-hunspell
```

These targets download:

- `data/raw/azwiki-latest-pages-articles.xml.bz2`
- `data/raw/az.aff`
- `data/raw/az.dic`

### 4. Add the local orthography markdown

Place your locally prepared orthography source at:

```sh
data/raw/list_of_words.md
```

This file is intentionally not fetched by `make`, because it is a local/project-specific input.

### 5. Optionally record checksums

```sh
make checksums
```

### 6. Run a smoke test first

```sh
make wiki-smoke
```

This validates the parser and weighting on a small slice of the Wikipedia dump.

### 7. Build the full ranked dictionary

```sh
make ranked-dict
```

Final outputs:

- `artifacts/az_ranked.combined`
- `artifacts/main_az_ranked.dict`

## Main Build Targets

### Baseline unigram-only build

```sh
make baseline
```

Outputs:

- `artifacts/az_wordlist.combined`
- `artifacts/main_az.dict`

### Build valid-form lists only

```sh
make forms
```

Outputs:

- `data/intermediate/hunspell_stems.txt`
- `data/intermediate/hunspell_forms.txt`
- `data/intermediate/backfill_forms.txt`
- `data/intermediate/valid_forms.txt`

### Smoke test on a small slice of Wikipedia

```sh
make wiki-smoke
```

This runs a limited pass over the first 2,000 article pages and builds:

- `data/intermediate/wiki_counts_smoke.sqlite`
- `artifacts/az_ranked_smoke.combined`

Use this first to validate the parser and weighting without waiting for the full corpus.

### Full ranked dictionary build

```sh
make ranked-dict
```

Outputs:

- `data/intermediate/wiki_counts.sqlite`
- `artifacts/az_ranked.combined`
- `artifacts/main_az_ranked.dict`

## Checksums

To record the exact local inputs you used:

```sh
make checksums
```

This writes:

- `manifests/checksums.local.txt`

## How The Ranked Pipeline Works

1. Extract and clean orthography words from `list_of_words.md`
2. Expand the subset of Hunspell suffix rules that are actually defined in `az.aff`
3. Build:
   - `valid_forms.txt` for corpus filtering
   - `backfill_forms.txt` for compact unseen-word fallback
4. Stream the compressed Wikipedia XML dump page by page
5. Strip wiki markup and tokenize text
6. Keep only tokens present in `valid_forms.txt`
7. Count unigrams and bigrams into SQLite in batches
8. Build a weighted `.combined` dictionary from:
   - seen corpus words
   - top bigrams
   - unseen backfill forms at low weight
9. Compile the final `.dict`

## Notes On Memory And Scale

- the Wikipedia dump is processed as a compressed stream
- the pipeline does not need to unpack the full XML to disk
- unigram and bigram counts are flushed to SQLite in batches instead of being kept fully in RAM
- this is meant to be transparent and reproducible, not a black-box one-off build

## What Gets Committed

Recommended to commit:

- scripts
- README and docs
- input manifests and SHA256 checksums
- final generated `.combined` and `.dict` if licensing allows

Recommended not to commit:

- very large raw corpora
- copyrighted source books or PDFs unless you are sure redistribution is allowed
- temporary extraction artifacts

## Should Downloading Be In Make?

For this repo, yes, but only for the public inputs.

- good fit: Wikipedia dump and Mozilla Hunspell files
- not a good fit: local orthography markdown derived from a source you prepare yourself

That is why the repo includes optional `make fetch-*` targets for the public files, while `list_of_words.md` stays a manual local input.
