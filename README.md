# Laya TryOn

English | [简体中文](README.zh-CN.md)

> Say what you need, get an outfit picked for you, see it on your own body from the front, side and back — and know how far to trust the picture.

Laya TryOn is a self-hosted **virtual try-on** website for real people:

- **Pick clothes by talking**: the [laya](https://github.com/NandhaKishorM/laya) decision model chooses the best item from the wardrobe in 0.2–0.4 s (CPU is enough).
- **Multi-view try-on on real people**: built on [FASHN VTON v1.5](https://github.com/fashn-AI/fashn-vton-1.5). Upload your own front / side / back photos and every view gets dressed; first preview after ~0.8 s, about 8 s per view on an RTX 4060.
- **Garment length from the size chart**: picks a size from your height and measurements, works out where the hem should fall, draws the garment at its real length and keeps your real legs below the hem.
- **Fidelity first**: only the clothes are repainted, never your body; photos and body data are checked at upload, and implausible numbers are marked untrusted.
- **Reliability score + result check**: every image gets a 0–100 score with itemised deductions; after generation the hem position and leg width are measured, and images that contradict the size chart or the original photo are flagged as failing the check.
- **Bring your own generation models (optional)**: plug in any OpenAI-compatible image model to generate mock garments and sample people, or a plugin for a video model to render turnaround videos.

The web UI is in Chinese.

![Screenshot](docs/images/screenshot.png)

## Quick start

Requirements: **Python 3.10+**, an **NVIDIA GPU with 8 GB+ VRAM**, about **15 GB of disk** (dependencies + models). It also installs without a GPU, but each try-on then takes minutes.

```bash
git clone <this repo> laya-tryon && cd laya-tryon

# 1. One-shot install: two isolated virtual environments, GPU build of torch, FASHN weights, laya models, then a self-check
python scripts/setup.py                # add --hf-mirror inside mainland China

# 2. Start (runs in the background, opens the browser when ready)
python scripts/run.py start            # stop: python scripts/run.py stop
```

Open <http://127.0.0.1:7860>, pick a bundled sample person on the left and a garment on the right, or type a request such as "明天要去面试" ("I have a job interview tomorrow").

On Windows you can also use `scripts\setup.ps1` / `scripts\start.ps1`; on Linux / macOS `scripts/setup.sh` / `scripts/start.sh`. If something goes wrong, run `python scripts/doctor.py` first, then see [Troubleshooting](docs/en/troubleshooting.md).

## Documentation

| Document | Contents |
|---|---|
| [Deployment](docs/en/deployment.md) | Hardware, install options, LAN access, Linux servers / cloud GPUs, upgrading and uninstalling |
| [Architecture](docs/en/architecture.md) | Components, request flow, the try-on pipeline (masking, size-chart length, result check), performance, key design decisions |
| [Data model](docs/en/data-model.md) | Garment (e-commerce fields) and person models, value provenance, connecting real e-commerce data |
| [Validation and scoring](docs/en/validation-and-scoring.md) | Photo checks, body-data credibility, size selection, reliability score and result check rules |
| [Generation models](docs/en/generation.md) | Plugging in your own image / video models for mock garments, sample people and turnaround videos |
| [API](docs/en/api.md) | All HTTP endpoints |
| [Development](docs/en/development.md) | Code layout, tests, tools, extending the project |
| [Troubleshooting](docs/en/troubleshooting.md) | Common problems |

## Project layout

```
app/                backend (FastAPI)
  server.py         HTTP API
  tryon.py          FASHN VTON inference, repaintable-region masks, result check
  fitting.py        size selection and garment-length plan
  validation.py     photo checks and body-data credibility
  scoring.py        reliability score
  providers.py      generation model interfaces (image / video, configured by the user)
  models.py         garment / person data models
  config.py         settings (environment variables / .env)
web/                frontend (plain HTML/CSS/JS, no build step)
catalog/            mock e-commerce listings (listing.json + flat-lay images)
samples/persons/    bundled sample people (AI-generated fictional people: three views + body profile)
scripts/            setup.py install / run.py start-stop / doctor.py self-check
tools/              generate mock garments and sample people (needs an image model)
plugins/            your own generation model implementations (not committed)
tests/              unit tests, API tests (no GPU), browser end-to-end test
docs/               documentation (en / zh-CN)
```

Created at runtime and not committed: `.venvs/` (virtual environments), `models/` (model weights), `data/` (uploaded people, results, logs).

## Known limitations

Try-on images are drawn by a generative model and are **not** a real fitting. The project tries hard to tell users what is real and what is inferred, but note:

- The image reflects garment length, but **does not simulate tightness**: an S and an XL look equally well-fitting.
- Body parts covered in the original photo (e.g. calves under long trousers) can only be inferred when trying on a short skirt. Users are advised at upload to wear a fitted T-shirt and shorts.
- Listings without a back image get no back view.
- For some styles (especially plain short-sleeve T-shirts) the model draws a cropped length; the result check detects this and marks the image unreliable.

See [Validation and scoring](docs/en/validation-and-scoring.md) and [Architecture](docs/en/architecture.md).

## License

The code is released under the [Apache License 2.0](LICENSE). Models and third-party projects it depends on have their own licenses; they are downloaded at install time and not redistributed here — see [NOTICE](NOTICE). The bundled sample people and garment images are AI-generated, and the listing data is fictional mock data.
