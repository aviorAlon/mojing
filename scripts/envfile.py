"""Minimal .env reader (KEY=VALUE lines, # comments). Real environment variables take precedence."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env(path=None):
    values = {}
    path = path or os.path.join(ROOT, ".env")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                value = value.split(" #", 1)[0].split("\t#", 1)[0]  # trailing comments
                values[key.strip()] = value.strip().strip('"').strip("'")
    values.update({k: v for k, v in os.environ.items() if k in values or k.startswith(("TRYON_", "LAYA_", "FASHN_", "HF_", "IMAGE_", "VIDEO_"))})
    return values
