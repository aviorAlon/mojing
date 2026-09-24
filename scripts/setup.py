#!/usr/bin/env python3
"""One-shot setup: virtual environments, dependencies, model weights, then an environment check.

    python scripts/setup.py                 # everything (auto-detects an NVIDIA GPU)
    python scripts/setup.py --cpu           # force CPU-only torch (works, but try-on takes minutes per image)
    python scripts/setup.py --hf-mirror     # download models through https://hf-mirror.com (mainland China)
    python scripts/setup.py --dev           # also install test tooling (pytest, playwright + chromium)
    python scripts/setup.py --skip-models   # dependencies only

Every step is idempotent: re-running skips what is already in place. Uses only the standard library, so any
Python >= 3.10 can run it.
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENVS = os.path.join(ROOT, ".venvs")
WEIGHTS = os.path.join(ROOT, "models", "fashn")
TORCH_TRYON = ("torch==2.6.0", "torchvision==0.21.0")
TORCH_LAYA = ("torch==2.14.0",)
TORCH_INDEX = "https://download.pytorch.org/whl/{}"


def banner(text):
    print(f"\n\033[1m==> {text}\033[0m", flush=True)


def venv_python(name):
    sub = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
    return os.path.join(VENVS, name, *sub)


def run(cmd, env=None, check=True):
    print("   $", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, env=env)
    if check and result.returncode != 0:
        sys.exit(f"\n命令失败（exit {result.returncode}）：{' '.join(cmd)}\n请查看上面的输出，或参考 docs/zh-CN/troubleshooting.md（English: docs/en/troubleshooting.md）")
    return result.returncode


def pip(name, *args, env=None, check=True):
    return run([venv_python(name), "-m", "pip", "install", "--disable-pip-version-check", *args], env=env, check=check)


def has_nvidia_gpu():
    smi = shutil.which("nvidia-smi")
    if not smi:
        return False
    return subprocess.run([smi, "-L"], capture_output=True).returncode == 0


def make_venv(name):
    if os.path.isfile(venv_python(name)):
        print(f"   {name}: 已存在，跳过创建")
        return
    run([sys.executable, "-m", "venv", os.path.join(VENVS, name)])
    run([venv_python(name), "-m", "pip", "install", "--quiet", "--upgrade", "pip"])


def install_tryon(device, dev, env):
    banner(f"换装服务依赖（torch {device}）")
    make_venv("tryon")
    index = TORCH_INDEX.format("cu124" if device == "cuda" else "cpu")
    pip("tryon", *TORCH_TRYON, "--index-url", index, env=env)
    pip("tryon", "-r", os.path.join(ROOT, "requirements", "tryon.txt"), env=env)
    if dev:
        pip("tryon", "-r", os.path.join(ROOT, "requirements", "dev.txt"), env=env)
        run([venv_python("tryon"), "-m", "playwright", "install", "chromium"], env=env, check=False)


def install_laya(env):
    banner("laya 决策服务依赖（CPU）")
    make_venv("laya")
    # CPU wheels keep this environment small; fall back to PyPI's default build if the CPU index lacks the version
    if pip("laya", *TORCH_LAYA, "--index-url", TORCH_INDEX.format("cpu"), env=env, check=False) != 0:
        pip("laya", *TORCH_LAYA, env=env)
    pip("laya", "-r", os.path.join(ROOT, "requirements", "laya.txt"), env=env)


def download_models(env):
    banner("下载 FASHN VTON v1.5 权重（约 2GB）")
    script = f"""
import os
from huggingface_hub import hf_hub_download
w = {WEIGHTS!r}
os.makedirs(os.path.join(w, "dwpose"), exist_ok=True)
if not os.path.isfile(os.path.join(w, "model.safetensors")):
    hf_hub_download("fashn-ai/fashn-vton-1.5", "model.safetensors", local_dir=w)
for f in ("yolox_l.onnx", "dw-ll_ucoco_384.onnx"):
    if not os.path.isfile(os.path.join(w, "dwpose", f)):
        hf_hub_download("fashn-ai/DWPose", f, local_dir=os.path.join(w, "dwpose"))
from fashn_human_parser import FashnHumanParser
FashnHumanParser(device="cpu")  # caches the human-parser weights
print("   FASHN 权重就绪：", w)
"""
    run([venv_python("tryon"), "-c", script], env=env)

    banner("预热 laya 模型（3 个 checkpoint，首次会下载）")
    run([venv_python("laya"), "-c", "from laya import Router; Router(device='cpu', preload=True); print('   laya 模型就绪')"], env=env)


def write_env_file():
    target, example = os.path.join(ROOT, ".env"), os.path.join(ROOT, ".env.example")
    if not os.path.isfile(target) and os.path.isfile(example):
        shutil.copyfile(example, target)
        print("   已生成 .env（从 .env.example 复制，可按需修改）")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cpu", action="store_true", help="安装 CPU 版 torch（没有 NVIDIA 显卡时自动选择）")
    parser.add_argument("--dev", action="store_true", help="安装测试工具（pytest、playwright）")
    parser.add_argument("--hf-mirror", action="store_true", help="通过 hf-mirror.com 下载模型")
    parser.add_argument("--skip-models", action="store_true", help="只装依赖，不下载模型")
    parser.add_argument("--only", choices=["tryon", "laya", "models"], help="只执行某一步")
    args = parser.parse_args()

    if sys.version_info < (3, 10):
        sys.exit(f"需要 Python >= 3.10，当前是 {sys.version.split()[0]}")
    env = dict(os.environ)
    if args.hf_mirror:
        env["HF_ENDPOINT"] = "https://hf-mirror.com"
    device = "cpu" if args.cpu or not has_nvidia_gpu() else "cuda"
    if device == "cpu" and not args.cpu:
        print("没有检测到 NVIDIA 显卡，将安装 CPU 版 torch（换装会非常慢，建议在有 GPU 的机器上部署）")

    t0 = time.time()
    os.makedirs(VENVS, exist_ok=True)
    steps = [args.only] if args.only else ["tryon", "laya"] + ([] if args.skip_models else ["models"])
    if "tryon" in steps:
        install_tryon(device, args.dev, env)
    if "laya" in steps:
        install_laya(env)
    if "models" in steps:
        download_models(env)
    write_env_file()

    banner("环境自检")
    code = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "doctor.py")]).returncode
    print(f"\n安装完成，用时 {int(time.time() - t0)} 秒。启动：python scripts/run.py start")
    sys.exit(code)


if __name__ == "__main__":
    main()
