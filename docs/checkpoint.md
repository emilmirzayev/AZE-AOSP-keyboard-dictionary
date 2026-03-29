# Progress Checkpoint

Date:

- 2026-03-29

Purpose:

- snapshot the current repo state so work can resume quickly later

## What Is In Place

### Dictionary and bigram pipeline

The existing Azerbaijani dictionary pipeline remains intact:

- orthography extraction
- Hunspell form expansion
- Wikipedia unigram and bigram counting
- ranked `.combined` and compiled `.dict` output

### LM data-preparation pipeline

The repo now has an initial LM preparation workflow:

- `scripts/normalize_lm_corpus.py`
  - reads mixed local corpora from a manifest
  - supports `jsonl`, `jsonl.gz`, `json`, `json.gz`, `csv`, `parquet`, `txt`, `txt.gz`
  - writes normalized JSONL
- `scripts/build_lm_text_corpus.py`
  - cleans normalized documents
  - chunks text into manageable lines
  - exact-dedupes through SQLite
  - writes `train.txt` and `valid.txt`
- `scripts/train_sentencepiece_tokenizer.py`
  - trains SentencePiece
  - reserves FUTO control tokens like `<XBU>`, `<XBC>`, `<XEC>`, `<CHAR_A>` to `<CHAR_Z>`

Related files:

- `manifests/lm_sources.example.json`
- `docs/lm-pipeline.md`

### Reproducible environment

The repo now has a shared environment setup for both the current dictionary work and future LM work:

- `docker/Dockerfile.cpu`
  - recommended default
  - intended for dictionary builds, corpus prep, tokenizer training, and LM smoke tests
- `docker/Dockerfile.gpu`
  - scaffold for future remote GPU training
- `requirements/base.txt`
- `requirements/lm.txt`
- `requirements/gpu-train.txt`
- `docs/development-environment.md`

Make targets were added for:

- `venv`
- `venv-train`
- `docker-build-cpu`
- `docker-build-gpu`
- `docker-shell-cpu`
- `docker-shell-gpu`
- `docker-run-cpu`
- `docker-run-gpu`
- `docker-make-cpu`
- `docker-make-gpu`

## Important Research Conclusions

### FUTO current behavior

Based on FUTO docs and current public source:

- transformer finetuning from user typing is effectively disabled right now
- adaptive learning mainly happens through dictionary history and n-gram updates
- dictionary and bigram logic remain the backbone even when a transformer is present

### FUTO compatibility constraints

For a future FUTO-importable LM, the current documented and source-visible constraints are:

- SentencePiece tokenizer
- whitespace as suffix
- GGUF with KeyboardLM metadata
- FUTO control-token contract

The main hard problem for Azerbaijani is still non-ASCII keyboard-character handling in the correction-oriented transformer path.

## What Has Not Been Done Yet

- actual transformer training script
- training config files
- checkpoint/resume logic for model training
- GGUF export pipeline
- Azerbaijani-aware correction-data generation
- end-to-end test of Docker image builds on this machine
- actual tokenizer training run in this environment

## Verified So Far

Verified:

- Python syntax for the new LM scripts
- CLI help for the new LM scripts
- LM normalization and corpus-build smoke test on tiny temporary data
- Make target expansion for the new LM and Docker targets
- shell syntax for `scripts/build_aosp_binary.sh`

Not verified yet:

- real `docker build`
- real tokenizer training run in this workspace
- Parquet ingestion on real data
- any transformer training

## Resume Plan

Recommended first steps tomorrow:

1. Build the CPU container:
   - `make docker-build-cpu`
2. Copy and edit the LM manifest:
   - `cp manifests/lm_sources.example.json manifests/lm_sources.local.json`
3. Put local corpora under `data/raw/lm/...`
4. Run normalization and inspect volume:
   - `make docker-make-cpu TARGET=lm-normalize`
5. Build the text corpus:
   - `make docker-make-cpu TARGET=lm-build-corpus`
6. Train a first tokenizer:
   - `make docker-make-cpu TARGET=lm-train-tokenizer`
7. Inspect tokenization quality on common Azerbaijani forms
8. Only after that, start adding a transformer-training stage

## Good First Data Direction

Planned corpus mix:

- Azerbaijani Wikipedia text
- news corpora
- butabytes-style large text sources
- any additional Azerbaijani public text you gather later

Preferred source formats for large data:

- `jsonl`
- `jsonl.gz`
- `parquet`
- plain text

Avoid giant monolithic JSON arrays when possible.

## Notes For GitHub Commit

Safe to commit:

- scripts
- docs
- Docker files
- requirements files
- example manifests

Do not commit:

- large corpora under `data/raw/`
- generated outputs under `data/intermediate/`
- local manifests like `manifests/lm_sources.local.json`

## Working Assumptions

- keep dictionary and LM work in the same repo for now
- use Docker as the main reproducible environment
- use the local machine for data prep and smoke tests
- plan for real transformer training on a stronger remote GPU machine later
