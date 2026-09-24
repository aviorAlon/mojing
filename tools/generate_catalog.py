#!/usr/bin/env python3
"""Generate mock e-commerce listings (every field marked source="mock") with the image model you configured.

    .venvs/tryon/bin/python tools/generate_catalog.py                    # items in tools/catalog_spec.json missing from catalog/
    .venvs/tryon/bin/python tools/generate_catalog.py --only mock_tee_white --force
    .venvs/tryon/bin/python tools/generate_catalog.py --spec my_spec.json --out my_catalog/

Needs an image provider (IMAGE_API_KEY or IMAGE_PROVIDER in .env, see docs/generation.md). The front flat-lay is
generated first and passed as the reference for the back, so both sides show the same garment.
"""
import argparse
import io
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from PIL import Image  # noqa: E402

from envfile import load_env  # noqa: E402

os.environ.update({k: v for k, v in load_env().items() if k not in os.environ})

import providers  # noqa: E402
from models import GarmentImage, Listing, ModelReference, SizeChart, SizeRow, Sku, Val  # noqa: E402


def flat_lay_prompt(item, side):
    detail = item["front"] if side == "front" else f"{item['front']}的背面。{item['back']}"
    prompt = (f"电商商品平铺图：一件{detail}。{'正面' if side == 'front' else '背面'}朝上平铺在纯白背景上，俯拍，完整展示整件衣服，"
              "衣服居中且四周留白，没有模特、没有衣架、没有其他物品和文字水印，光线均匀柔和，写实商品摄影。")
    if side == "back":
        prompt += "必须和参考图是同一件衣服：颜色、面料、版型、尺寸比例完全一致，只是翻过来展示背面。"
    return prompt


def mock(value):
    return Val(value=value, source="mock")


def build_listing(item):
    chart = item["size_chart"]
    ref = item["model_reference"]
    return Listing(
        id=item["id"], platform="mock", item_id=item["id"], title=item["title"], brand=mock("MOCK"), price=mock(item["price"]),
        category_path=item["category_path"], category=item["category"], gender=mock("female"),
        images=[GarmentImage(file="front.jpg", kind="flat_lay", view="front", source="mock"),
                GarmentImage(file="back.jpg", kind="flat_lay", view="back", source="mock")],
        skus=[Sku(color=item["color"], size=s, stock=100) for s in chart["rows"]],
        attributes={k: mock(v) for k, v in item["attributes"].items()},
        size_chart=SizeChart(basis="garment", source="mock",
                             rows=[SizeRow(size=s, measures=dict(zip(chart["columns"], vals))) for s, vals in chart["rows"].items()]),
        model_reference=ModelReference(**ref, source="mock"), occasions=mock(item["occasions"]),
        raw={"note": "mock listing for testing; not real platform data"},
    )


def save_jpg(data, path):
    Image.open(io.BytesIO(data)).convert("RGB").save(path, quality=92)


def make_incomplete_example(catalog):
    """A listing with only a front image, to exercise the 'feature off because data is missing' paths."""
    folder, src = os.path.join(catalog, "mock_incomplete_tee"), os.path.join(catalog, "mock_tee_white", "front.jpg")
    if os.path.isfile(os.path.join(folder, "listing.json")) or not os.path.isfile(src):
        return
    os.makedirs(folder, exist_ok=True)
    shutil.copyfile(src, os.path.join(folder, "front.jpg"))
    listing = Listing(id="mock_incomplete_tee", platform="mock", item_id="mock_incomplete_tee", title="（数据不全示例）白色短袖T恤",
                      category="top", category_path=["女装", "T恤"], price=mock(59), occasions=mock("居家、日常"),
                      images=[GarmentImage(file="front.jpg", kind="flat_lay", view="front", source="mock")],
                      raw={"note": "only a front image: no back image, attributes, size chart or model reference"})
    with open(os.path.join(folder, "listing.json"), "w", encoding="utf-8") as f:
        f.write(listing.model_dump_json(indent=2))
    print("saved mock_incomplete_tee")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spec", default=os.path.join(ROOT, "tools", "catalog_spec.json"))
    parser.add_argument("--out", default=os.path.join(ROOT, "catalog"))
    parser.add_argument("--only", nargs="*", help="只生成这些 id")
    parser.add_argument("--force", action="store_true", help="已存在也重新生成")
    args = parser.parse_args()

    with open(args.spec, encoding="utf-8") as f:
        spec = json.load(f)
    todo = [p for p in spec if (not args.only or p["id"] in args.only)
            and (args.force or not os.path.isfile(os.path.join(args.out, p["id"], "listing.json")))]
    if todo:
        try:
            image = providers.image_provider()
        except providers.ProviderNotConfigured as e:
            sys.exit(str(e))
        print(f"用 {image.name} 生成 {len(todo)} 件商品（{len(todo) * 2} 张图）")
        for item in todo:
            folder = os.path.join(args.out, item["id"])
            os.makedirs(folder, exist_ok=True)
            front = image.generate(flat_lay_prompt(item, "front"))
            back = image.generate(flat_lay_prompt(item, "back"), reference=front)
            save_jpg(front, os.path.join(folder, "front.jpg"))
            save_jpg(back, os.path.join(folder, "back.jpg"))
            with open(os.path.join(folder, "listing.json"), "w", encoding="utf-8") as f:
                f.write(build_listing(item).model_dump_json(indent=2))
            print("saved", item["id"])
    else:
        print("没有需要生成的商品（用 --force 重新生成）")
    make_incomplete_example(args.out)


if __name__ == "__main__":
    main()
