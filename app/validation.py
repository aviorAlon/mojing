"""Credibility checks for user photos and body data.

Thresholds are deliberately loose: they are meant to catch photos that will make try-on fail and numbers that
are implausible for a human body, not to police normal variation.
"""
import cv2
import numpy as np

from models import BodyProfile, Person, PhotoCheck, TrustIssue, Val

# OpenPose-18 body keypoints as produced by DWPose
NOSE, NECK, R_SHO, R_ELB, R_WRI, L_SHO, L_ELB, L_WRI, R_HIP, R_KNEE, R_ANK, L_HIP, L_KNEE, L_ANK, R_EYE, L_EYE = range(16)
VIS = 0.3
# FASHN human parser labels
BG, FACE, HAIR, TOP, DRESS, SKIRT, PANTS, BELT, BAG, HAT, SCARF, GLASSES, ARMS, HANDS, LEGS, FEET, TORSO = range(17)
VIEW_LABEL = {"front": "正面", "side": "侧面", "back": "背面"}


def check_photo(analysis: dict, declared_view: str) -> PhotoCheck:
    blocking, warnings, metrics = [], [], {}
    w, h = analysis["orig_size"]
    arr, seg, kp, sc = analysis["arr"], analysis["seg"], analysis["kp"], analysis["score"]
    ih, iw = seg.shape[:2]

    if min(w, h) < 400:
        blocking.append(f"照片分辨率太低（{w}×{h}），短边至少 400 像素")
    elif min(w, h) < 700:
        warnings.append(f"照片分辨率偏低（{w}×{h}），细节可能不清楚")
    sharpness = cv2.Laplacian(cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY), cv2.CV_64F).var()
    metrics["sharpness"] = round(float(sharpness), 1)
    if sharpness < 15:
        blocking.append("照片模糊，请对焦后重拍")
    elif sharpness < 50:
        warnings.append("照片有些模糊")

    body_scores = sc[:, 1:14].mean(axis=1) if len(sc) else np.array([])
    people = int((body_scores > VIS).sum())
    metrics["people"] = people
    if people == 0:
        blocking.append("没有检测到人")
        return PhotoCheck(view=declared_view, passed=False, blocking=blocking, warnings=warnings, metrics=metrics)
    if people > 1:
        blocking.append("画面中有多个人，请只拍自己")
    i = int(np.argmax(body_scores))
    k, s = kp[i], sc[i]
    seen = lambda j: s[j] > VIS  # noqa: E731

    person = seg != BG
    ys, xs = np.nonzero(person)
    top, bottom = ys.min(), ys.max()
    height_px = bottom - top
    metrics["person_height_ratio"] = round(height_px / ih, 3)
    if top <= ih * 0.01:
        blocking.append("头顶被裁到了，请全身入镜")
    if bottom >= ih * 0.99 or not (seen(R_ANK) or seen(L_ANK)):
        blocking.append("脚被裁到了，请全身入镜（头顶到脚底都要在画面里）")
    if height_px < ih * 0.5:
        warnings.append("人在画面里太小，请站近一些")

    # view: face pixels vs hair pixels tell front/back; shoulder span relative to height tells side
    face_px, hair_px = (seg == FACE).sum(), (seg == HAIR).sum()
    face_ratio = face_px / max(face_px + hair_px, 1)
    shoulder = abs(k[R_SHO][0] - k[L_SHO][0]) / height_px if seen(R_SHO) and seen(L_SHO) else 0.0
    metrics.update(face_ratio=round(float(face_ratio), 3), shoulder_span=round(float(shoulder), 3))
    if shoulder < 0.12:
        detected = "side"
    elif face_ratio < 0.12:
        detected = "back"
    else:
        detected = "front"
    metrics["detected_view"] = detected
    if detected != declared_view:
        blocking.append(f"这张看起来是{VIEW_LABEL[detected]}照，但放在了「{VIEW_LABEL[declared_view]}」位置")

    # exposure: how much real skin the model can rely on
    knee_y = max(k[R_KNEE][1] if seen(R_KNEE) else 0, k[L_KNEE][1] if seen(L_KNEE) else 0)
    if knee_y:
        shin = slice(int(knee_y), int(bottom))
        skin, cloth = (seg[shin] == LEGS).sum(), np.isin(seg[shin], [PANTS, SKIRT, DRESS]).sum()
        metrics["shin_skin_ratio"] = round(float(skin / max(skin + cloth, 1)), 3)
        if cloth > skin:
            warnings.append("小腿被裤子遮住了：换短裙/短裤时腿部只能由 AI 推测。建议穿短裤拍")
    arm_skin, sleeve = (seg == ARMS).sum(), (seg == TOP).sum()
    metrics["arm_skin_ratio"] = round(float(arm_skin / max(person.sum(), 1)), 4)
    if arm_skin < person.sum() * 0.01:
        warnings.append("手臂被袖子遮住了：换短袖/背心时手臂只能由 AI 推测。建议穿短袖拍")

    # proportions for cross-checking the entered body data (joint-to-joint, relative to standing height)
    if seen(R_HIP) and seen(L_HIP):
        hip_y = (k[R_HIP][1] + k[L_HIP][1]) / 2
        row = seg[int(hip_y)]
        body_row = np.isin(row, [TORSO, TOP, DRESS, SKIRT, PANTS, BELT, LEGS])
        cols = np.nonzero(body_row)[0]
        metrics["hip_width_ratio"] = round(float((cols.max() - cols.min()) / height_px), 3) if len(cols) else None
        ank = [k[j][1] for j in (R_ANK, L_ANK) if seen(j)]
        if ank:
            metrics["leg_ratio"] = round(float((np.mean(ank) - hip_y) / height_px), 3)
    metrics["shoulder_ratio"] = round(float(shoulder), 3)
    colors = arr[np.isin(seg, [TOP, DRESS])]
    if len(colors) > 500:
        metrics["top_color"] = [int(c) for c in np.median(colors, axis=0)]

    return PhotoCheck(view=declared_view, passed=not blocking, blocking=blocking, warnings=warnings, metrics=metrics)


def _num(v: Val):
    return float(v.value) if v.known else None


def check_profile(p: BodyProfile) -> list[TrustIssue]:
    issues = []

    def bad(level, field, msg):
        issues.append(TrustIssue(level=level, field=field, message=msg))

    ranges = {"height_cm": (120, 220, "身高"), "weight_kg": (30, 200, "体重"), "chest_cm": (60, 160, "胸围"),
              "waist_cm": (45, 160, "腰围"), "hip_cm": (60, 170, "臀围"), "shoulder_cm": (28, 60, "肩宽")}
    val = {}
    for f, (lo, hi, name) in ranges.items():
        x = _num(getattr(p, f))
        if x is not None and not lo <= x <= hi:
            bad("untrusted", f, f"{name} {x:g} 超出正常人体范围（{lo}–{hi}）")
        else:
            val[f] = x
    h, wt = val.get("height_cm"), val.get("weight_kg")
    if h and wt:
        bmi = wt / (h / 100) ** 2
        if not 13 <= bmi <= 50:
            bad("untrusted", "weight_kg", f"身高体重对应 BMI {bmi:.1f}，不符合人体范围")
        elif not 16 <= bmi <= 40:
            bad("suspicious", "weight_kg", f"BMI {bmi:.1f} 偏离常见范围，请确认身高体重")
    c, wa, hp, sh = val.get("chest_cm"), val.get("waist_cm"), val.get("hip_cm"), val.get("shoulder_cm")
    if wa and c and hp and wa > c + 15 and wa > hp + 15:
        bad("suspicious", "waist_cm", "腰围明显大于胸围和臀围，请确认")
    if wa and h and not 0.33 <= wa / h <= 0.8:
        bad("suspicious", "waist_cm", "腰围和身高的比例不常见，请确认")
    if sh and h and not 0.19 <= sh / h <= 0.31:
        bad("suspicious", "shoulder_cm", "肩宽和身高的比例不常见，请确认")
    return issues


def cross_check(p: BodyProfile, checks: dict[str, PhotoCheck]) -> tuple[list[TrustIssue], dict[str, Val]]:
    """Compare entered numbers with what the photos show; photo measurements are only used for checking."""
    issues, measured = [], {}
    front = checks.get("front")
    h = _num(p.height_cm)
    if front and h:
        m = front.metrics
        if m.get("shoulder_ratio"):
            measured["shoulder_cm"] = Val(value=round(m["shoulder_ratio"] * h, 1), source="measured", confidence=0.6,
                                          note="肩关节间距，比量体肩宽略小")
        if m.get("hip_width_ratio"):
            width = m["hip_width_ratio"] * h
            measured["hip_width_cm"] = Val(value=round(width, 1), source="measured", confidence=0.5, note="正面胯部宽度（含衣物）")
            hip = _num(p.hip_cm)
            if hip and not 2.2 <= hip / width <= 4.2:
                issues.append(TrustIssue(level="suspicious", field="hip_cm", message=f"填写的臀围 {hip:g}cm 和照片中的胯宽（约 {width:.0f}cm）对不上"))
            wt = _num(p.weight_kg)
            if wt:
                bmi = wt / (h / 100) ** 2
                # an average build (BMI ~23) measures ~33cm across the hips in these photos
                if (bmi >= 35 and width < 36) or (bmi >= 30 and width < 31) or (bmi <= 18.5 and width > 40):
                    issues.append(TrustIssue(level="suspicious", field="weight_kg", message="填写的身高体重和照片中的体型差别很大"))
        if m.get("leg_ratio"):
            measured["leg_ratio"] = Val(value=m["leg_ratio"], source="measured", confidence=0.6)
            if not 0.36 <= m["leg_ratio"] <= 0.58:
                issues.append(TrustIssue(level="suspicious", field="photo", message="照片中的腿长比例异常，可能是广角畸变或拍摄角度问题"))
        sh = _num(p.shoulder_cm)
        if sh and m.get("shoulder_ratio") and not 0.7 <= (m["shoulder_ratio"] * h) / sh <= 1.2:
            issues.append(TrustIssue(level="suspicious", field="shoulder_cm", message="填写的肩宽和照片中的肩宽对不上"))

    legs = {v: c.metrics.get("leg_ratio") for v, c in checks.items() if c.metrics.get("leg_ratio") and v != "side"}
    if len(legs) == 2 and abs(legs["front"] - legs["back"]) > 0.06:
        issues.append(TrustIssue(level="suspicious", field="photo", message="正面和背面照的身体比例不一致，可能不是同一次拍摄"))
    tops = [np.array(c.metrics["top_color"], dtype=np.uint8) for c in checks.values() if c.metrics.get("top_color")]
    if len(tops) >= 2:
        lab = [cv2.cvtColor(t.reshape(1, 1, 3), cv2.COLOR_RGB2LAB).reshape(3).astype(float) for t in tops]
        if max(np.linalg.norm(a - b) for a in lab for b in lab) > 40:
            issues.append(TrustIssue(level="suspicious", field="photo", message="几张照片里穿的衣服不一样，请用同一身衣服拍三视图"))
    return issues, measured


def assess(person: Person) -> Person:
    issues = check_profile(person.profile)
    extra, measured = cross_check(person.profile, person.photo_checks)
    person.issues, person.measured = issues + extra, measured
    required = [person.profile.gender, person.profile.height_cm, person.profile.weight_kg]
    if any(i.level == "untrusted" for i in person.issues):
        person.trust = "untrusted"
    elif not all(v.known for v in required):
        person.trust = "unverified"
    elif person.issues:
        person.trust = "suspicious"
    else:
        person.trust = "trusted"
    return person
