PYTHON ?= python3

RAW_MD := data/raw/list_of_words.md
WIKI_DUMP := data/raw/azwiki-latest-pages-articles.xml.bz2
HUNSPELL_AFF := data/raw/az.aff
HUNSPELL_DIC := data/raw/az.dic

ORTHO_WORDS := data/intermediate/orthography_words.txt
ORTHO_SINGLE := data/intermediate/orthography_single_tokens.txt
HUNSPELL_STEMS := data/intermediate/hunspell_stems.txt
HUNSPELL_FORMS := data/intermediate/hunspell_forms.txt
BACKFILL_FORMS := data/intermediate/backfill_forms.txt
VALID_FORMS := data/intermediate/valid_forms.txt
WIKI_DB := data/intermediate/wiki_counts.sqlite
SMOKE_DB := data/intermediate/wiki_counts_smoke.sqlite

BASE_COMBINED := artifacts/az_wordlist.combined
BASE_DICT := artifacts/main_az.dict
RANKED_COMBINED := artifacts/az_ranked.combined
RANKED_DICT := artifacts/main_az_ranked.dict
SMOKE_COMBINED := artifacts/az_ranked_smoke.combined

.PHONY: fetch-wiki fetch-hunspell fetch-public-data baseline baseline-extract baseline-filter baseline-combined baseline-dict forms wiki-smoke wiki-counts ranked-combined ranked-dict ranked checksums

fetch-wiki:
	sh scripts/download_wikipedia_dump.sh $(WIKI_DUMP)

fetch-hunspell:
	sh scripts/download_hunspell.sh $(HUNSPELL_AFF) $(HUNSPELL_DIC)

fetch-public-data: fetch-wiki fetch-hunspell

baseline: baseline-extract baseline-filter baseline-combined baseline-dict

baseline-extract:
	$(PYTHON) scripts/extract_markdown_wordlist.py $(RAW_MD) -o $(ORTHO_WORDS)

baseline-filter:
	$(PYTHON) scripts/filter_single_tokens.py $(ORTHO_WORDS) -o $(ORTHO_SINGLE)

baseline-combined:
	$(PYTHON) scripts/build_aosp_combined.py $(ORTHO_SINGLE) -o $(BASE_COMBINED) --version 18

baseline-dict:
	sh scripts/build_aosp_binary.sh $(BASE_COMBINED) $(BASE_DICT)

forms: baseline-extract baseline-filter
	$(PYTHON) scripts/build_valid_forms.py --orthography $(ORTHO_SINGLE) --dic $(HUNSPELL_DIC) --aff $(HUNSPELL_AFF) --hunspell-stems-output $(HUNSPELL_STEMS) --hunspell-output $(HUNSPELL_FORMS) --backfill-output $(BACKFILL_FORMS) -o $(VALID_FORMS)

wiki-smoke: forms
	$(PYTHON) scripts/extract_wikipedia_counts.py --dump $(WIKI_DUMP) --allowlist $(VALID_FORMS) --db $(SMOKE_DB) --max-pages 2000 --flush-pages 250 --progress-every 250
	$(PYTHON) scripts/build_ranked_combined.py --db $(SMOKE_DB) --valid-forms $(VALID_FORMS) --backfill-forms $(BACKFILL_FORMS) -o $(SMOKE_COMBINED) --version 18

wiki-counts: forms
	$(PYTHON) scripts/extract_wikipedia_counts.py --dump $(WIKI_DUMP) --allowlist $(VALID_FORMS) --db $(WIKI_DB)

ranked-combined: wiki-counts
	$(PYTHON) scripts/build_ranked_combined.py --db $(WIKI_DB) --valid-forms $(VALID_FORMS) --backfill-forms $(BACKFILL_FORMS) -o $(RANKED_COMBINED) --version 18

ranked-dict: ranked-combined
	sh scripts/build_aosp_binary.sh $(RANKED_COMBINED) $(RANKED_DICT)

ranked: ranked-dict

checksums:
	$(PYTHON) scripts/write_checksums.py $(RAW_MD) $(WIKI_DUMP) $(HUNSPELL_AFF) $(HUNSPELL_DIC)
