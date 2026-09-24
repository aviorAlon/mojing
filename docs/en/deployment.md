# Deployment Guide

## Hardware and system requirements

| Item | Minimum | Recommended | Notes |
|---|---|---|---|
| GPU | NVIDIA, 8GB VRAM | 12GB+, or a data-center card (A10/A100/H100) | Try-on inference uses about 4GB; leave headroom when sharing the GPU with desktop apps and the browser |
| RAM | 16GB | 32GB | laya preloading its 3 checkpoints uses about 3–4GB |
| Disk | 15GB | 30GB | Two virtual environments ~7GB, FASHN weights ~2GB, laya models ~3GB |
| Python | 3.10 | 3.11 | Only one system Python is needed to run the setup script |
| OS | Windows 10/11, Linux x86_64 | — | Fully verified on Windows 10 + RTX 4060; Linux uses the same scripts |

Reference timings per view (Standard mode, 10 steps): RTX 4060 about 8s; RTX 4090 estimated about 3s; H100 estimated 1–2s. The last two are estimates based on FASHN's published numbers (about 5s for 30 steps on an H100) and have not been measured.

Without an NVIDIA GPU, `setup.py` installs the CPU build of torch automatically. The website opens and works normally, but each view takes several minutes to try on, so this is only useful for UI debugging.

## Installation

```bash
python scripts/setup.py [options]
```

| Option | Effect |
|---|---|
| (none) | Install everything: virtual environments, dependencies, model weights, then run the self-check |
| `--hf-mirror` | Download models through `https://hf-mirror.com` (mainland China networks) |
| `--cpu` | Force the CPU build of torch |
| `--dev` | Also install pytest, playwright and Chromium (for running tests) |
| `--skip-models` | Install dependencies only, don't download models |
| `--only tryon\|laya\|models` | Run a single step (e.g. re-download models: `--only models`) |

What the setup script does:

1. Creates the try-on service's virtual environment in `.venvs/tryon`: installs torch 2.6 with CUDA 12.4 if an NVIDIA GPU is detected, then `requirements/tryon.txt` (FASHN VTON is pinned to a verified commit).
2. Creates the decision service's virtual environment in `.venvs/laya`: CPU torch 2.14 + laya 0.3.20. laya and the try-on service need incompatible torch versions, so they must be kept apart.
3. Downloads the FASHN VTON v1.5 weights to `models/fashn/`, the DWPose pose models to `models/fashn/dwpose/`, and the human-parsing model into the Hugging Face cache.
4. Pre-warms the laya models (3 checkpoints packed in one Hugging Face repo, downloaded into the cache).
5. Generates `.env` from `.env.example`.
6. Runs the `scripts/doctor.py` self-check.

Every step can be rerun; completed parts are skipped or pass quickly.

### Offline / internal-network installation

Run `setup.py` once on a machine with internet access, then copy the following to the same locations on the target machine:

- `models/fashn/`
- The Hugging Face cache directory (default `~/.cache/huggingface/hub`, on Windows `%USERPROFILE%\.cache\huggingface\hub`), which contains the laya models and the human-parsing model
- pip on the target machine can point to an internal mirror: `pip config set global.index-url <mirror URL>`

Then run `python scripts/setup.py` on the target machine. Existing model files are skipped.

## Starting and stopping

```bash
python scripts/run.py start            # start both services in the background, open the browser when ready (--no-browser to skip)
python scripts/run.py status           # show processes and health checks
python scripts/run.py stop
python scripts/run.py restart
```

- laya decision service: `127.0.0.1:8765` by default
- Try-on website: `127.0.0.1:7860` by default
- Logs: `data/logs/laya.log`, `data/logs/tryon.log`
- The first start loads the models and preprocesses the wardrobe and sample people, which takes about 30–90 seconds

## Configuration

All configuration lives in `.env` (see `.env.example` for full descriptions). Environment variables take precedence over `.env`.

| Variable | Default | Description |
|---|---|---|
| `TRYON_HOST` / `TRYON_PORT` | `127.0.0.1` / `7860` | Website listen address |
| `TRYON_ENGINE` | `on` | `off` skips loading the try-on model and runs only the UI and API (for debugging without a GPU) |
| `FASHN_WEIGHTS` | `models/fashn` | FASHN weights directory |
| `LAYA_HOST` / `LAYA_PORT` | `127.0.0.1` / `8765` | laya service address |
| `LAYA_DEVICE` | `cpu` | Putting it on the GPU competes with the try-on model for VRAM and isn't needed |
| `DATA_DIR` | `data` | Uploaded people, results, videos, logs |
| `CATALOG_DIR` | `catalog` | Garment catalog |
| `SAMPLES_DIR` | `samples/persons` | Bundled sample people |
| `HF_ENDPOINT` | — | Hugging Face mirror URL |
| `IMAGE_API_BASE` / `IMAGE_API_KEY` / `IMAGE_MODEL` / `IMAGE_PROVIDER` | not configured | Image generation model (mock garments, mock sample people), see [Generation models](generation.md) |
| `VIDEO_PROVIDER` / `VIDEO_SECONDS` | not configured / `5` | Video generation model (turnaround video), see [Generation models](generation.md) |

## LAN access

Set `TRYON_HOST=0.0.0.0` in `.env` and run `run.py restart`; devices on the same network can then open `http://<this machine's IP>:7860`.

> **Note**: the website has **no login or access control**. Anyone who can reach it can upload photos and see people uploaded by others. Only use it this way on a trusted network; before exposing it to the internet, put an authenticating reverse proxy in front of it (e.g. Nginx + Basic Auth or single sign-on).

The laya service doesn't need to be exposed; keep `LAYA_HOST=127.0.0.1`.

## Linux server / cloud GPU

```bash
sudo apt install -y python3 python3-venv git   # Ubuntu / Debian
git clone <this repo> /opt/laya-tryon && cd /opt/laya-tryon
python3 scripts/setup.py
python3 scripts/run.py start --no-browser
```

Make sure `nvidia-smi` produces output (the NVIDIA driver is installed). The CUDA toolkit doesn't need to be installed separately; the torch wheel ships its own CUDA runtime.

### Running permanently with systemd

`/etc/systemd/system/laya-tryon.service`:

```ini
[Unit]
Description=Laya TryOn
After=network-online.target

[Service]
Type=forking
User=tryon
WorkingDirectory=/opt/laya-tryon
ExecStart=/usr/bin/python3 scripts/run.py start --no-browser
ExecStop=/usr/bin/python3 scripts/run.py stop
Restart=on-failure
TimeoutStartSec=600

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now laya-tryon
```

### Start on boot on Windows

Create a task in Task Scheduler: trigger "At log on", action program `python`, arguments `scripts\run.py start --no-browser`, and "Start in" set to the project directory.

## Upgrading

```bash
git pull
python scripts/setup.py        # updates dependencies when they change; downloaded models are not downloaded again
python scripts/run.py restart
```

## Uninstalling

Stop the services and delete the project directory. To also clear the model cache, delete `models--convaiinnovations--*` and `models--fashn-ai--*` from the Hugging Face cache.
