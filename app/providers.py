"""Pluggable generation providers, configured by the user in .env.

Images (mock garments / sample people, used by tools/):
    IMAGE_API_BASE / IMAGE_API_KEY / IMAGE_MODEL   any OpenAI-compatible Images API
    IMAGE_PROVIDER=package.module:ClassName        or your own class implementing ImageProvider
Videos (turnaround video on the website):
    VIDEO_PROVIDER=package.module:ClassName        your own class implementing VideoProvider

Nothing is configured by default: calling a provider then raises ProviderNotConfigured with instructions.
See docs/generation.md.
"""
import base64
import importlib
import os
import sys
from typing import Protocol

import httpx


class ProviderNotConfigured(RuntimeError):
    pass


class ImageProvider(Protocol):
    name: str

    def generate(self, prompt: str, reference: bytes | None = None) -> bytes:
        """Return PNG/JPEG bytes. With `reference`, keep its subject (same garment / same person) and follow the prompt."""


class VideoProvider(Protocol):
    name: str

    def submit(self, prompt: str, first_frame: bytes, last_frame: bytes | None, seconds: int) -> str:
        """Start a video job (first frame required, last frame optional). Return a job id."""

    def poll(self, job_id: str) -> dict:
        """Return {"status": "pending" | "done" | "failed", "video": bytes (mp4, when done), "error": str (when failed)}."""


class OpenAIImageProvider:
    """OpenAI-compatible Images API: POST /images/generations, and /images/edits when a reference image is given."""

    def __init__(self, base_url: str, api_key: str, model: str, size: str = "1024x1536", transport=None):
        self.name = f"openai-compatible:{model}"
        self.model, self.size = model, size
        self.client = httpx.Client(base_url=base_url.rstrip("/"), headers={"Authorization": f"Bearer {api_key}"},
                                   timeout=300, transport=transport)

    def generate(self, prompt: str, reference: bytes | None = None) -> bytes:
        if reference is None:
            r = self.client.post("/images/generations", json={"model": self.model, "prompt": prompt, "size": self.size, "n": 1})
        else:
            r = self.client.post("/images/edits", data={"model": self.model, "prompt": prompt, "size": self.size, "n": "1"},
                                 files={"image": ("reference.png", reference, "image/png")})
        if r.status_code >= 400:
            raise RuntimeError(f"图片生成接口返回 {r.status_code}：{r.text[:300]}")
        item = r.json()["data"][0]
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])
        return self.client.get(item["url"]).content


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_class(spec: str):
    module, _, cls = spec.partition(":")
    if not module or not cls:
        raise ProviderNotConfigured(f"插件格式应为 package.module:ClassName，当前是 {spec!r}")
    for path in (os.path.join(ROOT, "plugins"), ROOT):  # user plugins live in plugins/ (see plugins/README.md)
        if path not in sys.path:
            sys.path.insert(0, path)
    try:
        return getattr(importlib.import_module(module), cls)()
    except (ImportError, AttributeError) as e:
        raise ProviderNotConfigured(f"加载插件 {spec} 失败：{e}")


def image_provider() -> ImageProvider:
    if spec := os.environ.get("IMAGE_PROVIDER"):
        return _load_class(spec)
    if key := os.environ.get("IMAGE_API_KEY"):
        return OpenAIImageProvider(os.environ.get("IMAGE_API_BASE", "https://api.openai.com/v1"), key,
                                   os.environ.get("IMAGE_MODEL", "gpt-image-1"), os.environ.get("IMAGE_SIZE", "1024x1536"))
    raise ProviderNotConfigured(
        "未配置图片生成模型：请在 .env 里设置 IMAGE_API_KEY（以及 IMAGE_API_BASE、IMAGE_MODEL，支持任何 OpenAI 兼容的 Images API），"
        "或用 IMAGE_PROVIDER=模块:类名 指定自己的实现。见 docs/generation.md")


def video_provider() -> VideoProvider:
    if spec := os.environ.get("VIDEO_PROVIDER"):
        return _load_class(spec)
    raise ProviderNotConfigured(
        "未配置视频生成模型：请在 .env 里用 VIDEO_PROVIDER=模块:类名 指定你自己的视频生成实现。见 docs/generation.md")


def video_status() -> dict:
    """For the UI: whether a video provider is configured, without contacting it."""
    try:
        return {"available": True, "provider": getattr(video_provider(), "name", "custom"), "reason": None}
    except Exception as e:  # not configured, or the plugin failed to import
        return {"available": False, "provider": None, "reason": str(e)}
