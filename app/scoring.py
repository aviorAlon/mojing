"""Reliability score for a try-on result: 100 minus itemised deductions, every one with a reason.

Two separate questions:
  visual — does the image show what this garment would look like on this person (from this angle)?
  fit    — is there enough trustworthy data to judge whether it fits? (the image itself does not simulate size)
"""
from models import Listing, Person

LEG_EXPOSING = {"短裙", "短裤", "中长款"}
ARM_EXPOSING = {"无袖", "短袖"}
PRINT_WORDS = ("印花", "文字", "字母", "logo", "条纹", "格纹", "碎花", "刺绣")  # not bare "字": "A字裙" is a cut, not text
HARD_WORDS = ("垂褶", "亮片", "透明", "蕾丝", "钩织", "网纱", "不对称", "单肩")
FIT_KEYS = {"upper": ("chest_cm", "胸围"), "lower": ("waist_cm", "腰围"), "overall": ("chest_cm", "胸围")}
FIT_KEYS_2 = {"lower": ("hip_cm", "臀围"), "overall": ("waist_cm", "腰围")}


def _grade(score):
    return "高" if score >= 80 else "中" if score >= 60 else "低"


def _attr(listing: Listing, key):
    v = listing.attributes.get(key)
    return v.value if v and v.known else None


def _exposes_legs(listing: Listing):
    length = _attr(listing, "length_type")
    if listing.category in ("skirt", "dress"):
        return None if length is None else length in LEG_EXPOSING | {"常规款"}
    if listing.category == "pants":
        return None if length is None else length in LEG_EXPOSING
    return False


def _exposes_arms(listing: Listing):
    if listing.category in ("pants", "skirt"):
        return False
    sleeve = _attr(listing, "sleeve")
    return None if sleeve is None else sleeve in ARM_EXPOSING


def visual_score(person: Person | None, listing: Listing, view: str, mode: str) -> dict:
    d = []
    check = person.photo_checks.get(view) if person else None
    if check is None:
        d.append((15, "这张照片没有经过质量检查"))
    else:
        m = check.metrics
        if any("模糊" in w for w in check.warnings):
            d.append((5, "照片有些模糊"))
        if any("分辨率" in w for w in check.warnings):
            d.append((5, "照片分辨率偏低"))
        legs, arms = _exposes_legs(listing), _exposes_arms(listing)
        if legs and m.get("shin_skin_ratio", 1) < 0.5:
            d.append((20, "这件会露出小腿，但你的照片里小腿被遮住了，腿部是 AI 推测的"))
        if arms and m.get("arm_skin_ratio", 1) < 0.01:
            d.append((15, "这件会露出手臂，但你的照片里手臂被遮住了，手臂是 AI 推测的"))
        if legs is None or arms is None:
            d.append((5, "商品缺少衣长/袖型信息，无法判断会露出哪些身体部位"))
    if view != "front":
        d.append((10, "侧面/背面的生成准确度低于正面"))
    img = listing.image("back" if view == "back" else "front")
    if img and img.kind == "on_model":
        d.append((10, "商品图是模特上身图，衣服细节需要从模特身上提取"))
    elif img and img.kind == "hanging":
        d.append((5, "商品图是挂拍图，版型可能有变形"))
    if img and img.source == "mock":
        d.append((10, "商品图是模拟生成的，不是真实商品照片"))
    if view == "side" and not listing.image("side"):
        d.append((5, "没有商品侧面图，侧面效果由正面图推测"))
    text = listing.title + " " + " ".join(str(v.value) for v in listing.attributes.values() if v.known)
    if any(w in text for w in HARD_WORDS):
        d.append((10, "垂褶、蕾丝、镂空等复杂工艺，生成时容易失真"))
    if any(w.lower() in text.lower() for w in PRINT_WORDS):
        d.append((5, "印花、文字、条纹等细节可能变形"))
    if mode == "turbo":
        d.append((10, "极速档步数少，细节较弱"))
    elif mode == "fast":
        d.append((3, "标准档的细节略逊于精细档"))
    return _result(d)


def fit_score(person: Person | None, listing: Listing) -> dict:
    d = []
    if person is None:
        d.append((40, "没有你的身材数据"))
    elif person.trust == "untrusted":
        d.append((60, "你的身材数据不可信，请修正"))
    elif person.trust == "suspicious":
        d.append((20, "你的身材数据有存疑项"))
    elif person.trust == "unverified":
        d.append((40, "身材数据不完整"))
    if person is not None:
        cat = listing.tryon_category
        for table in (FIT_KEYS, FIT_KEYS_2):
            if cat in table:
                key, label = table[cat]
                if not getattr(person.profile, key).known:
                    d.append((10, f"没填{label}，无法判断这件的松紧"))
    chart = listing.size_chart
    if chart is None:
        d.append((40, "商品没有尺码表"))
    else:
        if chart.source == "mock":
            d.append((10, "尺码表是模拟数据"))
        elif chart.source == "extracted" and (chart.confidence or 0) < 0.8:
            d.append((10, "尺码表是从图片识别的，可能有误"))
    if _attr(listing, "stretch") is None:
        d.append((10, "缺少面料弹力信息"))
    if _attr(listing, "fit") is None:
        d.append((5, "缺少版型信息（修身/宽松）"))
    if listing.model_reference is None:
        d.append((5, "没有模特身材参考"))
    return _result(d)


def _result(deductions):
    score = max(0, 100 - sum(p for p, _ in deductions))
    return {"score": score, "grade": _grade(score), "deductions": [{"points": p, "reason": r} for p, r in deductions]}


def _deduct(part, points, reason):
    part["deductions"].append({"points": points, "reason": reason})
    part["score"] = max(0, part["score"] - points)
    part["grade"] = _grade(part["score"])


def score_tryon(person: Person | None, listing: Listing, view: str, mode: str, plan: dict | None = None,
                qc: dict | None = None) -> dict:
    """plan: fitting summary (known before generating). qc: measurements of the generated image (after)."""
    visual = visual_score(person, listing, view, mode)
    if plan is not None and not plan.get("length_calibrated"):
        reason = plan.get("note") or plan.get("size_reason") or "缺少尺码或身高数据"
        _deduct(visual, 10, f"衣长没有按尺码表校准（{reason}），长短可能不准")
    if qc:
        diff = qc.get("length_diff_cm")
        if diff is not None and abs(diff) > 5:
            _deduct(visual, min(30, round(abs(diff))), f"生成的衣长比尺码表{'短' if diff < 0 else '长'}了约 {abs(diff):.0f}cm")
        ratio = qc.get("leg_width_ratio")
        if ratio is not None and not 0.9 <= ratio <= 1.1:
            pct = round(abs(1 - ratio) * 100)
            _deduct(visual, min(30, pct), f"露出的腿比原照片{'细' if ratio < 1 else '粗'}了约 {pct}%，身形被改变")
    fit = fit_score(person, listing)
    overall = round(visual["score"] * 0.6 + fit["score"] * 0.4)
    size_note = ""
    if plan and plan.get("size"):
        size_note = f"{plan['size_reason']}" + (f"，衣长按 {plan['length_cm']}cm 模拟。" if plan.get("length_calibrated") else "。")
    # a result that measurably contradicts the size chart or the person's body is unreliable, whatever else is good
    failures = [d["reason"] for d in visual["deductions"] if d["points"] >= 20 and d["reason"].startswith(("生成的", "露出的"))]
    if failures:
        overall = min(overall, 59)
    checked = "已对生成结果做衣长和腿形质检。" if qc is not None else "生成完成后会再做一次结果质检。"
    return {"view": view, "overall": overall, "grade": _grade(overall), "visual": visual, "fit": fit, "plan": plan,
            "qc": qc, "checked": qc is not None, "qc_failures": failures,
            "note": size_note + checked + "换装图体现衣长，但不模拟围度松紧。"}
