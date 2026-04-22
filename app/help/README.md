# Help Content Map

`app/help/` is the content source for welcome, embedded help, onboarding hints, and the human-readable error glossary.

## Files

- `content_ru.md` and `content_en.md`
  Full embedded help content for the Help window.
- `welcome_ru.md` and `welcome_en.md`
  Welcome and quick start copy in short and extended form.
- `glossary_ru.py` and `glossary_en.py`
  Stable error dictionary entries for runtime surfaces.
- `microcopy_ru.py` and `microcopy_en.py`
  Stable ids for tooltips, button hints, and onboarding microcopy.

## Integration Notes

- Markdown files are meant for full-page help and welcome rendering.
- Python dictionaries are meant for targeted UI insertion.
- Stable ids should stay aligned between Russian and English.
- Russian is the primary voice. English mirrors the same intent, not a word-for-word translation.
