# Development guide

## Environment

```bash
python scripts/setup.py --dev      # also installs pytest, playwright + Chromium
```

During development you can run the backend in the foreground and restart it manually after changes:

```bash
cd app
../.venvs/tryon/bin/python -m uvicorn server:app --port 7860          # Windows: ..\.venvs\tryon\Scripts\python
```

Start the laya service with `python scripts/run.py start` as usual, or run `.venvs/laya/bin/laya-serve` on its own (set `LAYA_PORT=8765`).

If you only touch the UI or API and don't need real try-on, set `TRYON_ENGINE=off` to skip loading the model — this works on machines without a GPU.

## Tests

```bash
.venvs/tryon/bin/python -m pytest tests               # unit + API tests, no GPU needed, ~5 s
python scripts/run.py start --no-browser
.venvs/tryon/bin/python -m pytest tests/e2e           # browser end-to-end test, needs the services ready
```

| File | Covers |
|---|---|
| `tests/test_validation.py` | Body data ranges, BMI, measurement relationships, cross-checking against photos, trust levels |
| `tests/test_fitting.py` | Size selection (measurements, stretch, usual size, middle size), length plan, arm masking rule |
| `tests/test_scoring.py` | Deduction rules, quality-check veto |
| `tests/test_data.py` | Integrity of the bundled garments and sample people |
| `tests/test_api.py` | HTTP API (temporary data directories, `TRYON_ENGINE=off`) |
| `tests/e2e/test_ui.py` | Three-view try-on in a real browser, checks the score and views skipped for missing data |

## Code layout

| Module | Responsibility | Needs GPU |
|---|---|---|
| `app/config.py` | Reads environment variables | No |
| `app/models.py` | Data models | No |
| `app/validation.py` | Photo checks, body-data credibility | No (inputs are pre-analysed results) |
| `app/fitting.py` | Size and garment length | No |
| `app/scoring.py` | Reliability score | No |
| `app/tryon.py` | Model loading, masking, sampling, quality check | Yes |
| `app/server.py` | HTTP layer that ties the modules together | Indirectly |

The rule logic (validation, fitting, scoring) is pure functions so it's easy to unit-test. Please add tests together with new rules.

## Adding bundled garments

Put `listing.json` and `front.jpg` in `catalog/<id>/`, plus `back.jpg` if there is a back image. Follow the format of the existing garments and [Data model](data-model.md) for `listing.json`. Afterwards run `pytest tests/test_data.py` to check.

You can also generate them in bulk with a configured image model, see [Generation models](generation.md#generating-mock-garments).

## Adding bundled sample people

Put `front.jpg` (side and back optional) and `profile.json` in `samples/persons/<id>/`. The easiest way: upload through "新建模特" (New person) on the website so the photos go through the checks, then copy `data/persons/<new id>/` to `samples/persons/<id>/` and change `id` in `profile.json` to the folder name. Ids may contain only lowercase letters, digits and underscores.

Sample people must be fictional (AI-generated). Do not add photos of real people.

## Conventions

- User-facing text is in Chinese; code, comments and commit messages are in English.
- No unnecessary comments in code; add one line only when *why* is not obvious.
- When data is missing, switch the feature off and explain why — never fill in guessed values.
