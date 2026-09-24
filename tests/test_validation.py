from models import BodyProfile, Person, PhotoCheck, Val
from validation import assess, check_profile, cross_check


def profile(**values):
    return BodyProfile(**{k: Val(value=v, source="user_input") for k, v in values.items()})


def levels(issues):
    return {(i.level, i.field) for i in issues}


def test_normal_profile_has_no_issues():
    assert check_profile(profile(gender="female", height_cm=162, weight_kg=55, waist_cm=70, hip_cm=94)) == []


def test_out_of_range_values_are_untrusted():
    issues = check_profile(profile(height_cm=300, weight_kg=10))
    assert ("untrusted", "height_cm") in levels(issues)
    assert ("untrusted", "weight_kg") in levels(issues)


def test_implausible_bmi_is_untrusted_and_unusual_bmi_suspicious():
    assert ("untrusted", "weight_kg") in levels(check_profile(profile(height_cm=160, weight_kg=150)))
    assert ("suspicious", "weight_kg") in levels(check_profile(profile(height_cm=160, weight_kg=110)))


def test_waist_larger_than_chest_and_hip_is_suspicious():
    issues = check_profile(profile(height_cm=165, weight_kg=60, chest_cm=85, waist_cm=110, hip_cm=90))
    assert ("suspicious", "waist_cm") in levels(issues)


def test_cross_check_flags_weight_that_contradicts_the_photo():
    photo = PhotoCheck(view="front", passed=True, metrics={"hip_width_ratio": 0.2, "shoulder_ratio": 0.18, "leg_ratio": 0.45})
    issues, measured = cross_check(profile(height_cm=160, weight_kg=150), {"front": photo})
    assert ("suspicious", "weight_kg") in levels(issues)
    assert measured["shoulder_cm"].source == "measured"


def test_cross_check_flags_front_and_back_taken_separately():
    front = PhotoCheck(view="front", passed=True, metrics={"leg_ratio": 0.42})
    back = PhotoCheck(view="back", passed=True, metrics={"leg_ratio": 0.52})
    issues, _ = cross_check(profile(height_cm=160, weight_kg=55), {"front": front, "back": back})
    assert any("不一致" in i.message for i in issues)


def test_trust_levels():
    base = dict(gender="female", height_cm=162, weight_kg=55)
    assert assess(Person(id="p1", profile=profile(**base))).trust == "trusted"
    assert assess(Person(id="p2", profile=profile(height_cm=162, weight_kg=55))).trust == "unverified"
    assert assess(Person(id="p3", profile=profile(**{**base, "weight_kg": 150}))).trust == "untrusted"
