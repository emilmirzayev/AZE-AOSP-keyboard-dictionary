# LM Pipeline

This repo now includes a separate pipeline for preparing Azerbaijani language-model training text without disturbing the existing dictionary build.

The first version focuses on:

- streaming large local datasets into one normalized JSONL format
- building cleaned train and validation text corpora
- training a SentencePiece tokenizer that matches FUTO's documented tokenizer requirements

It does **not** yet train the transformer itself or export a GGUF model.

## Output Stages

### 1. Normalized documents

Script:

- `scripts/normalize_lm_corpus.py`

Input:

- a local manifest JSON describing each corpus source

Output:

- `data/intermediate/lm/normalized_docs.jsonl`

Each line looks like:

```json
{"source":"news_azerbaijan","source_path":"/abs/path/to/file.parquet","record_id":"123","text":"..."}
```

This is the stable intermediate format. Once a dataset is normalized into this file, later stages do not care whether the original source was Parquet, JSONL, CSV, or plain text.

Supported source formats:

- `jsonl`
- `jsonl.gz`
- `json`
- `json.gz`
- `csv`
- `parquet` with optional `pyarrow`
- `txt`
- `txt.gz`

Important note for very large corpora:

- prefer `jsonl`, `jsonl.gz`, `parquet`, or plain text over giant monolithic JSON arrays
- `json` support exists, but it loads the full file in memory

### 2. Cleaned train and validation corpora

Script:

- `scripts/build_lm_text_corpus.py`

Input:

- normalized JSONL from stage 1

Outputs:

- `data/intermediate/lm/train.txt`
- `data/intermediate/lm/valid.txt`
- `data/intermediate/lm/dedupe.sqlite`

This stage:

- normalizes Unicode to NFC
- strips URLs and control characters
- collapses noisy whitespace
- splits long documents into paragraph or sentence-sized chunks
- exact-dedupes chunks through SQLite so large corpora can stay streamable
- deterministically sends a small fraction of unique chunks to validation

The text files are one chunk per line. That format is suitable for:

- SentencePiece tokenizer training
- causal language-model pretraining
- basic corpus inspection with shell tools

### 3. SentencePiece tokenizer

Script:

- `scripts/train_sentencepiece_tokenizer.py`

Input:

- `train.txt`

Outputs:

- `data/intermediate/lm/az_keyboard.model`
- `data/intermediate/lm/az_keyboard.vocab`

Default choices:

- `model_type=unigram`
- `vocab_size=12000`
- `character_coverage=1.0`
- `treat_whitespace_as_suffix=true`

Reserved tokens:

- `<XBU>`
- `<XBC>`
- `<XEC>`
- `<CHAR_A>` through `<CHAR_Z>`

Those match the control-token contract described in FUTO's LM docs and source for the current keyboard LM pipeline.

## Manifest Shape

Copy the example manifest and edit the local paths:

```sh
cp manifests/lm_sources.example.json manifests/lm_sources.local.json
```

Each source entry supports:

- `name`: stable identifier used in the normalized output
- `path` or `paths`: local file path or glob pattern
- `format`: `jsonl`, `jsonl.gz`, `json`, `json.gz`, `csv`, `parquet`, `txt`, `txt.gz`, or `auto`
- `text_fields`: list of fields to combine for structured sources
- `record_id_field`: optional per-record identifier field
- `field_joiner`: text used when combining multiple fields, default `\n\n`
- `records_path`: nested list path for JSON files whose records live below the root
- `text_mode`: for plain text sources, one of `document`, `lines`, or `paragraphs`
- `parquet_batch_size`: optional Parquet batch size

Examples:

- news JSONL with `title`, `summary`, and `text`
- Parquet rows with `title` and `text`
- one sentence per line text dumps
- paragraph-based plain text exports

## Make Targets

Run the full tokenizer-prep pipeline:

```sh
make lm-pipeline
```

Run stages individually:

```sh
make lm-normalize
make lm-build-corpus
make lm-train-tokenizer
```

Useful overrides:

```sh
make lm-normalize LM_MANIFEST=manifests/lm_sources.mybox.json
make lm-train-tokenizer LM_TOKENIZER_VOCAB_SIZE=15000
```

## Recommended First Pass

For a first Azerbaijani prototype:

1. Normalize all available sources into `normalized_docs.jsonl`
2. Build `train.txt` and `valid.txt`
3. Train tokenizers at `8000`, `12000`, and `15000` vocab
4. Inspect segmentation of common Azerbaijani forms like `Azərbaycan`, `gələcəyəm`, `şəhərlərdə`, and `özəlləşdirilməsi`

If the tokenizer looks healthy, the next step is transformer pretraining on `train.txt`, with `valid.txt` used only for held-out evaluation.

## Dependencies

Required:

- `python3`

Optional:

- `pyarrow` for Parquet input
- `sentencepiece` for tokenizer training

Example installs:

```sh
python3 -m pip install pyarrow sentencepiece
```

## Relation To FUTO

This pipeline matches the parts of FUTO's documented LM contract that are stable and reusable right now:

- SentencePiece tokenizer
- whitespace as suffix
- reserved keyboard control tokens

What still remains later:

- actual transformer training
- GGUF export
- FUTO Keyboard metadata fields
- Azerbaijani-aware correction data generation for non-ASCII keyboard characters
