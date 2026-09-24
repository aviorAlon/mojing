"""HTTP API with the try-on model disabled (TRYON_ENGINE=off, see conftest.py): no GPU needed."""
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture(scope="module")
def client():
    import server
    with TestClient(server.app) as c:
        yield c


def test_index_stamps_asset_versions(client):
    html = client.get("/").text
    assert "/static/app.js?v=" in html and "__V__" not in html


def test_status_reports_disabled_engine(client):
    s = client.get("/api/status").json()
    assert s["tryon"] == "disabled" and s["laya"] is False


def test_wardrobe_lists_catalog_with_capabilities(client):
    items = client.get("/api/wardrobe").json()
    assert len(items) >= 10
    assert all("capabilities" in x and x["url"] for x in items)


def test_sample_people_are_listed_and_read_only(client):
    people = {p["id"]: p for p in client.get("/api/persons").json()}
    assert {"sample_fitted", "sample_jeans"} <= set(people)
    assert people["sample_fitted"]["sample"] and people["sample_fitted"]["trust"] == "trusted"
    assert client.delete("/api/person/sample_fitted").status_code == 403


def test_score_has_one_entry_per_generatable_view(client):
    s = client.get("/api/score", params={"person_id": "sample_fitted", "item_id": "mock_incomplete_tee"}).json()
    assert set(s) == {"front", "side"}  # no back image -> no back view
    assert s["front"]["plan"]["length_calibrated"] is False
    full = client.get("/api/score", params={"person_id": "sample_fitted", "item_id": "mock_skirt_satin_midi"}).json()
    assert set(full) == {"front", "side", "back"} and full["front"]["plan"]["length_calibrated"]


def test_tryon_refuses_while_model_is_off(client):
    r = client.post("/api/tryon", json={"person_id": "sample_fitted", "item_id": "mock_tee_white"})
    assert r.status_code == 503


def test_back_view_without_back_image_is_rejected(client):
    r = client.post("/api/tryon", json={"person_id": "sample_fitted", "item_id": "mock_incomplete_tee", "view": "back"})
    assert r.status_code == 409


def test_add_and_delete_garment(client):
    buf = io.BytesIO()
    Image.new("RGB", (300, 400), "white").save(buf, "JPEG")
    r = client.post("/api/wardrobe", data={"name": "测试", "occasions": "测试", "category": "top"},
                    files={"image": ("f.jpg", buf.getvalue(), "image/jpeg")})
    item = r.json()["id"]
    assert any(x["id"] == item for x in client.get("/api/wardrobe").json())
    assert client.delete(f"/api/wardrobe/{item}").status_code == 200


def test_invalid_ids_are_rejected(client):
    assert client.get("/api/score", params={"person_id": "../x", "item_id": "mock_tee_white"}).status_code == 400
    assert client.get("/api/score", params={"person_id": "sample_fitted", "item_id": "../x"}).status_code == 400
