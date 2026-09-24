"""Data models for garments (e-commerce listings) and people.

Every value carries where it came from. Missing data stays missing: features that need it are switched off
or labelled, never filled with guesses.
"""
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

Source = Literal["platform", "extracted", "user_input", "measured", "derived", "mock", "missing"]
View = Literal["front", "side", "back"]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Val(BaseModel):
    value: Any = None
    source: Source = "missing"
    confidence: float | None = None  # only for extracted / measured values
    note: str | None = None

    @property
    def known(self) -> bool:
        return self.source != "missing" and self.value is not None


def missing() -> Val:
    return Val()


# ---------------------------------------------------------------- garment

Category = Literal["top", "outerwear", "pants", "skirt", "dress", "jumpsuit"]
TRYON_CATEGORY = {"top": "upper", "outerwear": "upper", "pants": "lower", "skirt": "lower", "dress": "overall", "jumpsuit": "overall"}
CATEGORY_LABEL = {"top": "上衣", "outerwear": "外套", "pants": "裤装", "skirt": "半身裙", "dress": "连衣裙", "jumpsuit": "连体裤"}


class GarmentImage(BaseModel):
    file: str
    kind: Literal["flat_lay", "hanging", "on_model", "detail"]
    view: Literal["front", "back", "side", "detail"]
    source: Source


class Sku(BaseModel):
    color: str
    size: str
    stock: int | None = None


class SizeRow(BaseModel):
    size: str
    measures: dict[str, float]  # cm, keys like length / chest / shoulder / sleeve / waist / hip


class SizeChart(BaseModel):
    basis: Literal["garment", "body"]  # garment = flat measurement of the piece; body = recommended body size
    rows: list[SizeRow]
    source: Source
    confidence: float | None = None


class ModelReference(BaseModel):
    """'模特身高168cm 体重48kg 穿S码' as printed on many listings."""
    height_cm: float
    weight_kg: float | None = None
    size: str
    source: Source
    confidence: float | None = None


ATTRIBUTE_KEYS = ["material", "thickness", "stretch", "fit", "length_type", "sleeve", "neckline", "season", "style"]


class Listing(BaseModel):
    id: str
    platform: str
    item_id: str
    url: str | None = None
    fetched_at: str = Field(default_factory=now)
    title: str
    brand: Val = Field(default_factory=missing)
    price: Val = Field(default_factory=missing)
    category_path: list[str] = []
    category: Category
    gender: Val = Field(default_factory=missing)
    images: list[GarmentImage]
    skus: list[Sku] = []
    attributes: dict[str, Val] = {}
    size_chart: SizeChart | None = None
    model_reference: ModelReference | None = None
    occasions: Val = Field(default_factory=missing)  # what laya matches user requests against
    raw: dict = {}

    def image(self, view: str) -> GarmentImage | None:
        order = {"flat_lay": 0, "hanging": 1, "on_model": 2}
        imgs = [i for i in self.images if i.view == view and i.kind in order]
        return min(imgs, key=lambda i: order[i.kind]) if imgs else None

    @property
    def tryon_category(self) -> str:
        return TRYON_CATEGORY[self.category]

    def capabilities(self) -> dict[str, dict]:
        """Which features this listing's data supports, with the reason when it doesn't."""
        def cap(ok, reason):
            return {"ok": bool(ok), "reason": None if ok else reason}

        chart = self.size_chart
        has_length = bool(chart and all("length" in r.measures for r in chart.rows))
        return {
            "tryon_front": cap(self.image("front"), "缺少正面商品图"),
            "tryon_back": cap(self.image("back"), "该商品没有背面图，无法生成背面效果"),
            "size_recommend": cap(chart, "该商品没有尺码表"),
            "length_mark": cap(has_length, "尺码表里没有衣长/裙长"),
            "fit_hint": cap(chart and self.attributes.get("stretch", missing()).known, "缺少尺码表或弹力信息"),
        }


# ---------------------------------------------------------------- person

class PhotoCheck(BaseModel):
    view: View
    passed: bool
    blocking: list[str] = []
    warnings: list[str] = []
    metrics: dict[str, Any] = {}


class BodyProfile(BaseModel):
    gender: Val = Field(default_factory=missing)
    height_cm: Val = Field(default_factory=missing)
    weight_kg: Val = Field(default_factory=missing)
    chest_cm: Val = Field(default_factory=missing)
    waist_cm: Val = Field(default_factory=missing)
    hip_cm: Val = Field(default_factory=missing)
    shoulder_cm: Val = Field(default_factory=missing)
    usual_top_size: Val = Field(default_factory=missing)
    usual_bottom_size: Val = Field(default_factory=missing)


class TrustIssue(BaseModel):
    level: Literal["untrusted", "suspicious"]
    field: str
    message: str


Trust = Literal["trusted", "suspicious", "untrusted", "unverified"]


class Person(BaseModel):
    id: str
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)
    version: int = 1
    views: dict[str, str] = {}  # view -> file name
    photo_checks: dict[str, PhotoCheck] = {}
    profile: BodyProfile = Field(default_factory=BodyProfile)
    measured: dict[str, Val] = {}
    trust: Trust = "unverified"
    issues: list[TrustIssue] = []
