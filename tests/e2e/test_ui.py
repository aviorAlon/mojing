"""Browser end-to-end test against a running server (needs the GPU model loaded).

    python scripts/run.py start --no-browser
    python -m pytest tests/e2e            # E2E_URL defaults to http://127.0.0.1:7860
"""
import json
import os
import urllib.request

import pytest

URL = os.environ.get("E2E_URL", "http://127.0.0.1:7860")


def _ready():
    try:
        with urllib.request.urlopen(URL + "/api/status", timeout=2) as r:
            return json.load(r).get("tryon") == "ready"
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _ready(), reason=f"no ready server at {URL} (start one with scripts/run.py)")


def test_try_on_all_views_with_score():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(URL)
        page.click("#model-grid button[data-id='sample_fitted']")
        page.click(".closet-grid .item[data-id=mock_dress_floral]")
        page.wait_for_function("document.querySelectorAll('.view-tab.done').length === 3", timeout=180_000)
        assert "已质检" in page.text_content("#score-pill")
        page.click(".closet-grid .item[data-id=mock_incomplete_tee]")
        page.wait_for_function("document.querySelectorAll('.view-tab.done').length === 2", timeout=180_000)
        assert page.locator(".view-tab.skipped").count() == 1
        browser.close()
        assert errors == []
