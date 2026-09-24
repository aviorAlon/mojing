#!/usr/bin/env python3
"""Generate a fictional sample person (front / side / back) with the image model you configured.

    .venvs/tryon/bin/python tools/generate_person.py --out samples/persons/sample_new \\
        --gender female --height 165 --weight 55 --look "大约30岁的普通中国女性，中等身材，黑色低马尾"

    # also register it on a running site, which runs the same photo checks and credibility checks as an upload
    .venvs/tryon/bin/python tools/generate_person.py --out /tmp/p1 --gender male --height 175 --weight 70 \\
        --look "大约35岁的普通中国男性，偏瘦，短发" --register http://127.0.0.1:7860

The front photo is generated first and passed as the reference for the side and back views, so all three show the
same person in the same outfit. Following the upload guidance, people wear a fitted T-shirt and shorts.
Needs an image provider (IMAGE_API_KEY or IMAGE_PROVIDER in .env, see docs/en/generation.md).
"""
import argparse
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import httpx  # noqa: E402
from PIL import Image  # noqa: E402

from envfile import load_env  # noqa: E402

os.environ.update({k: v for k, v in load_env().items() if k not in os.environ})

import providers  # noqa: E402

OUTFIT = "穿一件贴身的浅灰色纯色短袖圆领T恤（无图案无logo）和一条贴身的黑色短裤（到大腿中部），露出手臂和小腿，白色低帮运动鞋"
SCENE = ("从头顶到脚完整入镜，上下留少量空白，相机在胸口高度平视拍摄，没有广角畸变。背景是干净的浅色纯色墙面和浅灰色地面，"
         "光线均匀柔和。真实感手机实拍，不要摆拍感，不要滤镜，不要文字水印。")
POSES = {
    "front": "正面面对镜头自然站直，双脚与肩同宽，双臂自然下垂并稍微离开身体。",
    "side": "身体向右转90度，以纯侧面站立，头部朝向画面右侧，双臂自然下垂贴在身体两侧，双脚并拢自然站直。",
    "back": "转过身完全背对镜头站立，双臂自然下垂并稍微离开身体，双脚与肩同宽自然站直。",
}


def prompt(view, args):
    person = f"一位{args.look}，身高约{args.height:g}厘米，体重约{args.weight:g}公斤，{OUTFIT}。"
    if view == "front":
        return f"一张真实感的全身照：{person}{POSES['front']}{SCENE}"
    return (f"参考图中的同一个人、同一身衣服、同一个拍摄场景，身材比例、发型、光线和机位完全一致：{person}"
            f"现在{POSES[view]}{SCENE}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, help="输出目录（front.jpg / side.jpg / back.jpg）")
    parser.add_argument("--look", required=True, help="人物外观描述：年龄、身材、发型等，只描述虚构人物")
    parser.add_argument("--gender", required=True, choices=["female", "male"])
    parser.add_argument("--height", type=float, required=True, help="cm")
    parser.add_argument("--weight", type=float, required=True, help="kg")
    parser.add_argument("--views", nargs="+", default=["front", "side", "back"], choices=["front", "side", "back"])
    parser.add_argument("--register", metavar="URL", help="生成后上传到这个网站（会做照片检查和可信度评估）")
    args = parser.parse_args()
    if "front" not in args.views:
        sys.exit("必须包含 front")

    try:
        image = providers.image_provider()
    except providers.ProviderNotConfigured as e:
        sys.exit(str(e))
    os.makedirs(args.out, exist_ok=True)
    print(f"用 {image.name} 生成 {len(args.views)} 张照片")
    front = image.generate(prompt("front", args))
    photos = {"front": front}
    for view in args.views:
        if view != "front":
            photos[view] = image.generate(prompt(view, args), reference=front)
    for view, data in photos.items():
        path = os.path.join(args.out, f"{view}.jpg")
        Image.open(io.BytesIO(data)).convert("RGB").save(path, quality=95)
        print("saved", path)

    if args.register:
        files = {v: (f"{v}.jpg", open(os.path.join(args.out, f"{v}.jpg"), "rb"), "image/jpeg") for v in photos}
        form = {"gender": args.gender, "height_cm": str(args.height), "weight_kg": str(args.weight)}
        r = httpx.post(args.register.rstrip("/") + "/api/person", data=form, files=files, timeout=300)
        body = r.json()
        if r.status_code == 422:
            print("照片没通过检查：", json.dumps(body["checks"], ensure_ascii=False, indent=1))
            sys.exit(1)
        r.raise_for_status()
        print(f"已注册：id={body['id']}，可信度={body['trust']}，问题={[i['message'] for i in body['issues']]}")


if __name__ == "__main__":
    main()
