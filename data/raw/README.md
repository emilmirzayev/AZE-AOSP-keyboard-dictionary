# Raw Inputs

Place raw source files here.

Examples:

- `azwiki-latest-pages-articles.xml.bz2`
- `az.aff`
- `az.dic`
- `list_of_words.md`

This directory is mostly ignored by git so the repo can stay lightweight and legally cleaner.

One exception is:

- `list_of_words.md`, which is committed because it is a small build input derived from an Azerbaijani orthography dictionary word list

Record the origin and checksum of any file you use in `manifests/`.

Public files can be downloaded with:

- `make fetch-wiki`
- `make fetch-hunspell`
- `make fetch-public-data`

Large downloaded inputs such as the Wikipedia dump and Hunspell files should live here locally.
