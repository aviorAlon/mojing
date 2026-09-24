# Contributing

English | [简体中文](CONTRIBUTING.zh-CN.md)

Issues and pull requests are welcome.

## Issues

- Problems: include the output of `python scripts/doctor.py`, the relevant logs from `data/logs/`, your OS and GPU.
- Try-on quality: include the person photos (fictional people or photos you are allowed to share), the garment images, and the reliability score breakdown shown on the page.

## Pull requests

1. Branch off `master`; one PR does one thing.
2. Local setup: `python scripts/setup.py --dev`.
3. Changes to rule logic (`validation.py`, `fitting.py`, `scoring.py`) come with tests.
4. Run `python -m pytest tests` before submitting; everything must pass. If you changed the try-on pipeline, also run `tests/e2e` and attach before/after comparison images to the PR.
5. Update the relevant docs in both languages (`docs/en/` and `docs/zh-CN/`) and both changelogs.

## Principles

- **Fidelity first**: rather switch a feature off or give a low score than pass guessed data off as real.
- No photos of real people, copyrighted product images or model weights in the repository.
- User-facing text is Chinese; code, comments and commit messages are English.
