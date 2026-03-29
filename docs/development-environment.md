# Development Environment

This repo now has two environment options:

- Docker as the primary reproducible workflow
- a local Python virtual environment as a lighter fallback

The CPU Docker image is the recommended default for:

- dictionary and bigram builds
- corpus normalization
- tokenizer training
- LM smoke tests

The GPU Docker image is a scaffold for later transformer training on a stronger Linux/NVIDIA machine.

## Why Docker First

The repo now spans:

- Python scripts
- Java for `dicttool_aosp.jar`
- optional LM dependencies like `pyarrow` and `sentencepiece`
- future training dependencies like `transformers` and `accelerate`

Docker keeps those versions stable across your local machine and any future remote box.

## Files

- `docker/Dockerfile.cpu`
- `docker/Dockerfile.gpu`
- `requirements/base.txt`
- `requirements/lm.txt`
- `requirements/gpu-train.txt`

## CPU Container

Build it:

```sh
make docker-build-cpu
```

Open a shell in the repo with the repo bind-mounted:

```sh
make docker-shell-cpu
```

Run any existing repo target inside the container:

```sh
make docker-make-cpu TARGET=wiki-smoke
make docker-make-cpu TARGET=ranked-dict
make docker-make-cpu TARGET=lm-pipeline
```

Run an arbitrary command:

```sh
make docker-run-cpu DOCKER_COMMAND='python3 scripts/normalize_lm_corpus.py --help'
```

Notes:

- your local repo is mounted into `/workspace`
- raw corpora and generated outputs stay on the host filesystem
- the image only contains tools, not your 10 GB corpora

## GPU Container

This is meant for a remote Linux machine with NVIDIA drivers and Docker GPU support.

Build it:

```sh
make docker-build-gpu
```

Open a GPU-enabled shell:

```sh
make docker-shell-gpu
```

Run a command inside it:

```sh
make docker-run-gpu DOCKER_COMMAND='python3 -c "import torch; print(torch.cuda.is_available())"'
```

Important:

- `docker-shell-gpu` and `docker-run-gpu` expect `--gpus all`
- this is not expected to work on a normal macOS Docker setup
- use it later on a rented or remote Linux GPU box

## Local venv Fallback

Create the local environment:

```sh
make venv
```

This installs:

- core repo dependencies
- LM corpus/tokenizer dependencies

If you later want the future training stack in the same venv:

```sh
make venv-train
```

Activate it:

```sh
source .venv/bin/activate
```

## Recommended Workflow

For now:

1. Use `make docker-build-cpu`
2. Run dictionary and corpus-prep work through `make docker-make-cpu TARGET=...`
3. Keep all large corpora in `data/raw/` on the host
4. When we add actual transformer training, reuse the same repo inside a remote GPU container

That gives you one reproducible environment now without forcing heavy training onto your local machine.
