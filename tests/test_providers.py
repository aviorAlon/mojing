"""User-configured generation providers: missing configuration, plugins, OpenAI-compatible images, video API, tools."""
import base64
import json
import os
import subprocess
import sys

import httpx
import pytest
from fastapi.testclient import TestClient

import providers

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN_VARS = ("IMAGE_PROVIDER", "IMAGE_API_KEY", "VIDEO_PROVIDER")


@pytest.fixture
def clean_env(monkeypatch):
    for v in GEN_VARS:
        monkeypatch.delenv(v, raising=False)
    return monkeypatch


def test_nothing_configured_raises_with_instructions(clean_env):
    with pytest.raises(providers.ProviderNotConfigured, match="IMAGE_API_KEY"):
        providers.image_provider()
    with pytest.raises(providers.ProviderNotConfigured, match="VIDEO_PROVIDER"):
        providers.video_provider()
    assert providers.video_status()["available"] is False


def test_plugins_are_loaded_from_module_and_class(clean_env):
    clean_env.setenv("VIDEO_PROVIDER", "tests.fake_providers:FakeVideo")
    assert providers.video_provider().name == "fake-video"
    clean_env.setenv("VIDEO_PROVIDER", "tests.fake_providers:Missing")
    with pytest.raises(providers.ProviderNotConfigured, match="加载插件"):
        providers.video_provider()
    clean_env.setenv("VIDEO_PROVIDER", "no-colon")
    with pytest.raises(providers.ProviderNotConfigured, match="package.module:ClassName"):
        providers.video_provider()


def test_openai_compatible_images_generate_and_edit():
    seen = []

    def handler(request: httpx.Request):
        seen.append((request.url.path, request.headers["authorization"], request.headers["content-type"].split(";")[0]))
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(b"PNGDATA").decode()}]})

    p = providers.OpenAIImageProvider("https://example.test/v1", "sk-test", "img-model", transport=httpx.MockTransport(handler))
    assert p.generate("a shirt") == b"PNGDATA"
    assert p.generate("its back", reference=b"ref") == b"PNGDATA"
    assert seen == [("/v1/images/generations", "Bearer sk-test", "application/json"),
                    ("/v1/images/edits", "Bearer sk-test", "multipart/form-data")]


def test_openai_compatible_error_is_reported():
    p = providers.OpenAIImageProvider("https://example.test/v1", "k", "m",
                                      transport=httpx.MockTransport(lambda r: httpx.Response(401, text="bad key")))
    with pytest.raises(RuntimeError, match="401"):
        p.generate("x")


@pytest.fixture
def client():
    import server
    server._video.clear()
    with TestClient(server.app) as c:
        yield c, server
    server._video.clear()


def _fake_result(server):
    path = os.path.join(server.RESULTS_DIR, "test_front.jpg")
    with open(path, "wb") as f:
        f.write(b"jpg")
    return "/results/test_front.jpg"


def test_video_api_without_provider_returns_501(client, clean_env):
    c, server = client
    assert c.get("/api/video/config").json()["available"] is False
    r = c.post("/api/video", json={"front_url": _fake_result(server)})
    assert r.status_code == 501 and "VIDEO_PROVIDER" in r.json()["detail"]


def test_video_api_with_provider(client, clean_env):
    c, server = client
    clean_env.setenv("VIDEO_PROVIDER", "tests.fake_providers:FakeVideo")
    assert c.get("/api/video/config").json()["available"] is True
    job = c.post("/api/video", json={"front_url": _fake_result(server)}).json()["request_id"]
    assert c.get(f"/api/video/{job}").json()["status"] == "pending"
    done = c.get(f"/api/video/{job}").json()
    assert done["status"] == "done" and c.get(done["url"]).content.startswith(b"\x00\x00\x00\x18ftyp")
    assert c.post("/api/video", json={"front_url": "/results/nope.jpg"}).status_code == 400


def _run_tool(args, tmp_path, provider="tests.fake_providers:FakeImage"):
    env = {k: v for k, v in os.environ.items() if k not in GEN_VARS}
    if provider:
        env["IMAGE_PROVIDER"] = provider
    return subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")


def test_generate_catalog_tool(tmp_path):
    out = tmp_path / "catalog"
    r = _run_tool(["tools/generate_catalog.py", "--out", str(out), "--only", "mock_skirt_pleated"], tmp_path)
    assert r.returncode == 0, r.stderr
    listing = json.loads((out / "mock_skirt_pleated" / "listing.json").read_text(encoding="utf-8"))
    assert listing["size_chart"]["rows"] and (out / "mock_skirt_pleated" / "back.jpg").is_file()
    assert _run_tool(["tools/generate_catalog.py", "--out", str(tmp_path / "x"), "--only", "mock_tee_white"], tmp_path,
                     provider=None).returncode != 0


def test_generate_person_tool(tmp_path):
    out = tmp_path / "person"
    r = _run_tool(["tools/generate_person.py", "--out", str(out), "--look", "虚构的测试人物", "--gender", "female",
                   "--height", "165", "--weight", "55"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert {p.name for p in out.iterdir()} == {"front.jpg", "side.jpg", "back.jpg"}
    missing = _run_tool(["tools/generate_person.py", "--out", str(out), "--look", "x", "--gender", "female",
                         "--height", "165", "--weight", "55"], tmp_path, provider=None)
    assert missing.returncode != 0 and "IMAGE_API_KEY" in missing.stderr
