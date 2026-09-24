"""All runtime settings, read from environment variables (scripts/run.py loads them from .env)."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _path(name, default):
    value = os.environ.get(name, default)
    return value if os.path.isabs(value) else os.path.join(ROOT, value)


HOST = os.environ.get("TRYON_HOST", "127.0.0.1")
PORT = int(os.environ.get("TRYON_PORT", 7860))

LAYA_HOST = os.environ.get("LAYA_HOST", "127.0.0.1")
LAYA_PORT = int(os.environ.get("LAYA_PORT", 8765))
LAYA_URL = os.environ.get("LAYA_URL", f"http://{LAYA_HOST}:{LAYA_PORT}/v1/systemone")

FASHN_WEIGHTS = _path("FASHN_WEIGHTS", "models/fashn")
# "off" skips loading the try-on model (unit tests, or running the UI/API without a GPU)
ENGINE_ENABLED = os.environ.get("TRYON_ENGINE", "on").lower() != "off"

DATA_DIR = _path("DATA_DIR", "data")
CATALOG_DIR = _path("CATALOG_DIR", "catalog")
SAMPLES_DIR = _path("SAMPLES_DIR", "samples/persons")
WEB_DIR = os.path.join(ROOT, "web")

# Generation providers (images for tools/, video for the website) are configured in app/providers.py
VIDEO_SECONDS = int(os.environ.get("VIDEO_SECONDS", 5))
