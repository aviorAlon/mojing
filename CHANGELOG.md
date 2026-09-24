# Changelog

English | [简体中文](CHANGELOG.zh-CN.md)

This project follows [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-09-24

First open-source release.

### Features
- laya decisions: a one-sentence request → one item from the wardrobe (CPU, about 0.2–0.4 s).
- FASHN VTON v1.5 multi-view try-on (front / side / back), streamed previews, three speed modes.
- Size picked from the size chart and garment length simulated; only the clothes are repainted, the real body is kept.
- Photo checks at upload (full body, single person, view, sharpness, coverage hints) and body-data credibility assessment.
- Reliability score (visual / fit parts with itemised deductions) and post-generation result check (length deviation, leg-shape change).
- Data model: e-commerce garments and people, every value tagged with its source; features switch off when data is missing.
- One-shot setup (`scripts/setup.py`), start/stop (`scripts/run.py`), self-check (`scripts/doctor.py`).
- Optional generation model interfaces: OpenAI-compatible image models or plugins (mock garments, sample people), video plugins (turnaround videos).
