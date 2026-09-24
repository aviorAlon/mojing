"""The bundled catalog and sample people must load and be self-consistent."""
import os

import pytest

from models import Listing, Person

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, "catalog")
SAMPLES = os.path.join(ROOT, "samples", "persons")
LISTINGS = sorted(d for d in os.listdir(CATALOG) if os.path.isfile(os.path.join(CATALOG, d, "listing.json")))
PEOPLE = sorted(d for d in os.listdir(SAMPLES) if os.path.isdir(os.path.join(SAMPLES, d)))


@pytest.mark.parametrize("item", LISTINGS)
def test_listing_is_valid_and_images_exist(item):
    with open(os.path.join(CATALOG, item, "listing.json"), encoding="utf-8") as f:
        listing = Listing.model_validate_json(f.read())
    assert listing.id == item
    assert listing.image("front"), "every listing needs a front image"
    for img in listing.images:
        assert os.path.isfile(os.path.join(CATALOG, item, img.file))
    if listing.size_chart:
        keys = {k for r in listing.size_chart.rows for k in r.measures}
        assert all(set(r.measures) == keys for r in listing.size_chart.rows), "size chart rows must share columns"


def test_catalog_covers_missing_data_paths():
    caps = []
    for item in LISTINGS:
        with open(os.path.join(CATALOG, item, "listing.json"), encoding="utf-8") as f:
            caps.append(Listing.model_validate_json(f.read()).capabilities())
    assert any(not c["tryon_back"]["ok"] for c in caps), "keep at least one listing without a back image"
    assert any(not c["size_recommend"]["ok"] for c in caps), "keep at least one listing without a size chart"


@pytest.mark.parametrize("pid", PEOPLE)
def test_sample_person_is_complete(pid):
    with open(os.path.join(SAMPLES, pid, "profile.json"), encoding="utf-8") as f:
        person = Person.model_validate_json(f.read())
    assert person.id == pid
    for view, file in person.views.items():
        assert os.path.isfile(os.path.join(SAMPLES, pid, file))
    assert person.trust == "trusted"
