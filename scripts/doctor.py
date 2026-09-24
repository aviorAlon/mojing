#!/usr/bin/env python3
"""Check that everything needed to run is in place. Exit code 1 if something required is missing.

    python scripts/doctor.py
"""
import json
import os
import shutil
import socket
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from envfile import load_env  # noqa: E402

OK, WARN, FAIL = "\033[32m✔\033[0m", "\033[33m!\033[0m", "\033[31m✘\033[0m"
failures = 0


def report(status, text, hint=None):
    global failures
    failures += status == FAIL
    print(f"  {status} {text}" + (f"\n      → {hint}" if hint else ""))


def venv_python(name):
    sub = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
    return os.path.join(ROOT, ".venvs", name, *sub)


def probe(name, code):
    py = venv_python(name)
    if not os.path.isfile(py):
        return None
    out = subprocess.run([py, "-c", code], capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        return json.loads(out.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {"error": (out.stderr or out.stdout).strip()[-500:]}


TRYON_PROBE = r"""
import json, warnings
warnings.filterwarnings("ignore")
r = {}
import torch
r["torch"] = torch.__version__
r["cuda"] = torch.cuda.is_available()
if r["cuda"]:
    p = torch.cuda.get_device_properties(0)
    r["gpu"] = p.name; r["vram_gb"] = round(p.total_memory / 1024**3, 1)
    free, total = torch.cuda.mem_get_info(); r["vram_free_gb"] = round(free / 1024**3, 1)
import fashn_vton; r["fashn"] = True
from huggingface_hub import scan_cache_dir
try:
    r["parser_cached"] = any("fashn" in x.repo_id.lower() and "parser" in x.repo_id.lower() for x in scan_cache_dir().repos)
except Exception:
    r["parser_cached"] = None
print(json.dumps(r))
"""

LAYA_PROBE = r"""
import json, warnings
warnings.filterwarnings("ignore")
import laya
from huggingface_hub import scan_cache_dir
repos = [x.repo_id for x in scan_cache_dir().repos if x.repo_id.startswith("convaiinnovations/")]
print(json.dumps({"laya": laya.__version__, "models": repos}))
"""


def port_in_use(host, port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def main():
    if os.name == "nt":
        os.system("")  # turn on ANSI colours in older Windows consoles
    env = load_env()
    print(f"Laya TryOn 环境检查（{ROOT}）")

    print("\n[Python]")
    v = sys.version_info
    report(OK if v >= (3, 10) else FAIL, f"Python {v.major}.{v.minor}.{v.micro}", None if v >= (3, 10) else "需要 3.10 及以上")

    print("\n[换装服务 .venvs/tryon]")
    t = probe("tryon", TRYON_PROBE)
    if t is None:
        report(FAIL, "虚拟环境不存在", "运行 python scripts/setup.py")
    elif "error" in t:
        report(FAIL, "依赖导入失败", t["error"].splitlines()[-1] if t["error"] else "python scripts/setup.py --only tryon")
    else:
        report(OK, f"torch {t['torch']}")
        if t["cuda"]:
            report(OK if t["vram_gb"] >= 8 else WARN, f"GPU：{t['gpu']}，显存 {t['vram_gb']}GB（当前空闲 {t['vram_free_gb']}GB）",
                   None if t["vram_gb"] >= 8 else "建议 8GB 以上显存")
            if t["vram_free_gb"] < 4.5:
                report(WARN, "空闲显存不足 4.5GB，可能与其他程序争用", "关闭占用显存的程序（浏览器硬件加速、游戏等）")
        else:
            report(WARN, "没有可用的 CUDA，将用 CPU 推理（每张图需要数分钟）", "在有 NVIDIA 显卡的机器上运行 setup.py 会自动装 GPU 版")
        if t["parser_cached"] is False:
            report(WARN, "人体解析模型还没下载，首次启动时会自动下载", "python scripts/setup.py --only models")

    print("\n[模型权重]")
    weights = env.get("FASHN_WEIGHTS", "models/fashn")
    weights = weights if os.path.isabs(weights) else os.path.join(ROOT, weights)
    for rel, min_mb in (("model.safetensors", 1000), ("dwpose/yolox_l.onnx", 100), ("dwpose/dw-ll_ucoco_384.onnx", 100)):
        path = os.path.join(weights, rel)
        size = os.path.getsize(path) / 1024**2 if os.path.isfile(path) else 0
        report(OK if size >= min_mb else FAIL, f"{rel}（{size:.0f}MB）" if size else f"缺少 {rel}",
               None if size >= min_mb else "python scripts/setup.py --only models")

    print("\n[laya 决策服务 .venvs/laya]")
    lp = probe("laya", LAYA_PROBE)
    if lp is None:
        report(FAIL, "虚拟环境不存在", "运行 python scripts/setup.py")
    elif "error" in lp:
        report(FAIL, "laya 导入失败", "python scripts/setup.py --only laya")
    else:
        report(OK, f"laya {lp['laya']}")
        cached = "convaiinnovations/laya" in lp["models"]  # one bundle repo holds all three checkpoints (laya >= 0.3.9)
        report(OK if cached else WARN, f"模型缓存：{', '.join(lp['models']) or '无'}",
               None if cached else "首次启动会自动下载（约 3GB）；也可 python scripts/setup.py --only models")

    print("\n[端口]")
    for name, host, port in (("换装网站", env.get("TRYON_HOST", "127.0.0.1"), int(env.get("TRYON_PORT", 7860))),
                             ("laya", env.get("LAYA_HOST", "127.0.0.1"), int(env.get("LAYA_PORT", 8765)))):
        busy = port_in_use("127.0.0.1" if host == "0.0.0.0" else host, port)
        report(WARN if busy else OK, f"{name} {host}:{port}" + ("（已被占用：服务已在运行，或被其他程序占用）" if busy else " 空闲"))

    print("\n[可选：生成模型]")
    image = env.get("IMAGE_PROVIDER") or (f"OpenAI 兼容接口（{env.get('IMAGE_MODEL', 'gpt-image-1')}）" if env.get("IMAGE_API_KEY") else None)
    report(OK if image else WARN, f"图片模型：{image or '未配置'}", None if image else "只有生成模拟商品 / 模特的工具需要，见 docs/zh-CN/generation.md")
    video = env.get("VIDEO_PROVIDER")
    report(OK if video else WARN, f"视频模型：{video or '未配置'}", None if video else "只有转身视频需要，见 docs/zh-CN/generation.md")

    print("\n[磁盘]")
    free_gb = shutil.disk_usage(ROOT).free / 1024**3
    report(OK if free_gb > 5 else WARN, f"磁盘剩余 {free_gb:.0f}GB")

    print(f"\n{'全部必需项正常' if not failures else f'{failures} 项必需检查未通过'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
