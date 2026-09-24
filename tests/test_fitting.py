from fitting import fit_plan, pick_size
from models import BodyProfile, Listing, Person, SizeChart, SizeRow, Val


def listing(category="top", chart=True, stretch=None, sleeve="短袖"):
    rows = [SizeRow(size=s, measures={"length": 60 + i * 2, "chest": 96 + i * 4, "waist": 64 + i * 4, "hip": 90 + i * 4})
            for i, s in enumerate(["S", "M", "L", "XL"])]
    attrs = {k: Val(value=v, source="platform") for k, v in (("stretch", stretch), ("sleeve", sleeve)) if v}
    return Listing(id="x", platform="mock", item_id="x", title="t", category=category, images=[],
                   size_chart=SizeChart(basis="garment", rows=rows, source="platform") if chart else None, attributes=attrs)


def person(trust="trusted", **values):
    p = Person(id="p", profile=BodyProfile(**{k: Val(value=v, source="user_input") for k, v in values.items()}))
    p.trust = trust
    return p


def test_picks_smallest_size_that_fits_the_chest():
    row, reason = pick_size(listing(), person(chest_cm=100))  # needs garment chest >= 104
    assert row.size == "L" and "胸围" in reason


def test_stretch_allows_a_smaller_size():
    row, _ = pick_size(listing(stretch="高弹"), person(chest_cm=100))
    assert row.size == "M"


def test_usual_size_then_middle_size_as_fallbacks():
    assert pick_size(listing(), person(usual_top_size="s"))[0].size == "S"
    row, reason = pick_size(listing(), person())
    assert row.size == "L" and "中间码" in reason


def test_no_chart_means_no_size():
    assert pick_size(listing(chart=False), person(chest_cm=90)) == (None, "商品没有尺码表")


def test_plan_calibrates_length_only_with_height_and_chart():
    plan = fit_plan(listing(category="skirt"), person(height_cm=162, waist_cm=70))
    assert plan["summary"]["length_calibrated"] and plan["engine"]["start"] == "waist"
    assert not fit_plan(listing(), person(chest_cm=90))["summary"]["length_calibrated"]
    assert not fit_plan(listing(chart=False), person(height_cm=162))["summary"]["length_calibrated"]


def test_untrusted_profile_is_not_used_for_length():
    plan = fit_plan(listing(), person(trust="untrusted", height_cm=162))
    assert not plan["summary"]["length_calibrated"] and "不可信" in plan["summary"]["note"]


def test_arms_are_masked_only_for_sleeves_that_cover_them():
    assert not fit_plan(listing(sleeve="短袖"), None)["engine"]["mask_arms"]
    assert fit_plan(listing(sleeve="长袖"), None)["engine"]["mask_arms"]
    assert not fit_plan(listing(category="pants"), None)["engine"]["mask_arms"]
