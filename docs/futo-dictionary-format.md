# FUTO Dictionary Format Notes

Based on inspection of FUTO Keyboard source:

- editable source dictionaries are stored as `.combined` or `.combined.gz`
- manual import in the app expects a compiled binary `.dict`
- a dictionary header must include at least:
  - `dictionary`
  - `locale`
  - `version`
- `description` is also useful because FUTO reads it for display

## Example `.combined`

```text
dictionary=main:az,locale=az,description=Azerbaijani,date=1774800000,version=18
 word=gəl,f=140
  bigram=de,f=180
  bigram=ki,f=170
 word=gəldi,f=210
  bigram=və,f=150
 word=gəldim,f=190
 word=gəlmiş,f=175
 word=gələr,f=165
 word=gələcək,f=170
```

## Practical Meaning

- `word=` lines are explicit entries
- `f=` is the score/probability weight
- `bigram=` lines provide next-word prediction
- Azerbaijani morphology is not handled automatically by this format
- inflected forms should exist as actual entries

## Implication For This Project

A good Azerbaijani dictionary for FUTO should be built from:

- a validity source for real Azerbaijani forms
- a corpus for unigram frequencies
- a corpus for bigram frequencies

That is why the current lemma-only orthographic build is only a baseline, not the final target.
