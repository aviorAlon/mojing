from models import BodyProfile, GarmentImage, Listing, Person, PhotoCheck, Val
from scoring import score_tryon


def skirt(**extra):
    return Listing(id="s", platform="platform", item_id="s", title="半身裙", category="skirt",
                   images=[GarmentImage(file="front.jpg", kind="flat_lay", view="front", source="platform")],
                   attributes={"length_type": Val(value="短裙", source="platform")}, **extra)


def person(shin_skin_ratio):
    p = Person(id="p", profile=BodyProfile(height_cm=Val(value=162, source="user_input")))
    p.photo_checks = {"front": PhotoCheck(view="front", passed=True, metrics={"shin_skin_ratio": shin_skin_ratio})}
    p.trust = "trusted"
    return p


def reasons(score):
    return [d["reason"] for d in score["visual"]["deductions"]]


def test_covered_legs_cost_points_only_when_the_garment_shows_them():
    covered = score_tryon(person(0.0), skirt(), "front", "quality")
    bare = score_tryon(person(0.9), skirt(), "front", "quality")
    assert any("小腿被遮住" in r for r in reasons(covered))
    assert covered["visual"]["score"] == bare["visual"]["score"] - 20


def test_uncalibrated_length_is_deducted():
    s = score_tryon(person(0.9), skirt(), "front", "quality", plan={"length_calibrated": False, "note": "没有身高数据"})
    assert any("没有按尺码表校准" in r for r in reasons(s))


def test_failed_quality_check_caps_the_grade():
    s = score_tryon(person(0.9), skirt(), "front", "quality", plan={"length_calibrated": True, "size": "M", "size_reason": "x", "length_cm": 44},
                    qc={"length_diff_cm": -30})
    assert s["overall"] <= 59 and s["grade"] == "低" and s["qc_failures"]


def test_small_deviations_do_not_count():
    s = score_tryon(person(0.9), skirt(), "front", "quality", plan={"length_calibrated": True}, qc={"length_diff_cm": -3, "leg_width_ratio": 0.95})
    assert not s["qc_failures"] and s["checked"]
