"""Which size to simulate and how long the garment is on this person, from the listing's size chart.

Only data from the listing and the person's profile is used; when something is missing the plan says so instead
of guessing, and the try-on falls back to keeping the garment within the old clothes' outline.
"""
from models import Listing, Person

# ease added to the body measurement before comparing with a flat garment measurement (cm)
EASE = {"chest_cm": 4, "waist_cm": 0, "hip_cm": 2}
STRETCH_BONUS = {"高弹": 6, "微弹": 2}
KEYS = {"upper": [("chest", "chest_cm")], "lower": [("waist", "waist_cm"), ("hip", "hip_cm")],
        "overall": [("chest", "chest_cm"), ("waist", "waist_cm")]}
LONG_SLEEVES = {"长袖", "中袖", "七分袖"}


def _known(v):
    return v.value if v is not None and v.known else None


def pick_size(listing: Listing, person: Person | None):
    """Smallest size whose garment measurements fit the body (+ease). Returns (size row, reason) or (None, reason)."""
    chart = listing.size_chart
    if chart is None:
        return None, "商品没有尺码表"
    rows = chart.rows
    stretch = _known(listing.attributes.get("stretch"))
    bonus = STRETCH_BONUS.get(stretch, 0)
    profile = person.profile if person else None
    if profile:
        checks = [(g, getattr(profile, b).value, b) for g, b in KEYS[listing.tryon_category]
                  if getattr(profile, b).known and all(g in r.measures for r in rows)]
        if checks:
            for row in rows:
                if all(row.measures[g] + bonus >= body + EASE[b] for g, body, b in checks):
                    labels = "、".join({"chest": "胸围", "waist": "腰围", "hip": "臀围"}[g] for g, _, _ in checks)
                    return row, f"按你的{labels}推荐 {row.size} 码"
            return rows[-1], f"你的围度超过最大码，按 {rows[-1].size} 码模拟（可能偏紧）"
        usual = _known(profile.usual_bottom_size if listing.tryon_category == "lower" else profile.usual_top_size)
        match = next((r for r in rows if usual and r.size.upper() == str(usual).upper()), None)
        if match:
            return match, f"按你常穿的 {match.size} 码"
    middle = rows[len(rows) // 2]
    return middle, f"没有你的围度数据，按中间码 {middle.size} 模拟"


def fit_plan(listing: Listing, person: Person | None) -> dict:
    """What the try-on engine needs to size the garment, plus a human-readable summary."""
    cat = listing.tryon_category
    sleeve = _known(listing.attributes.get("sleeve"))
    plan = {"mask_arms": cat != "lower" and sleeve not in {"无袖", "短袖"}}
    summary = {"size": None, "size_reason": None, "length_cm": None, "length_calibrated": False, "note": None}

    row, reason = pick_size(listing, person)
    summary.update(size=row.size if row else None, size_reason=reason)
    height = _known(person.profile.height_cm) if person else None
    if person and person.trust == "untrusted":
        height = None
        summary["note"] = "身材数据不可信，没有按尺码表校准长度"
    length = row.measures.get("length") if row else None
    if row and length is None:
        summary["note"] = "尺码表里没有衣长，长度没有校准"
    elif row and height is None and not summary["note"]:
        summary["note"] = "没有身高数据，长度没有校准"
    if length and height:
        plan.update(length_cm=float(length), height_cm=float(height), start="waist" if cat == "lower" else "shoulder")
        summary.update(length_cm=length, length_calibrated=True)
    return {"engine": plan, "summary": summary}
