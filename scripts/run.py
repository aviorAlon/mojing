#!/usr/bin/env python3
"""Start / stop / inspect the two services (laya decision service + try-on web server).

    python scripts/run.py start      # start both in the background, wait until ready, print the URL
    python scripts/run.py stop
    python scripts/run.py status
    python scripts/run.py restart

Logs go to data/logs/, process ids to data/run/. Settings come from .env (see .env.example).
"""
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from envfile import load_env  # noqa: E402

RUN_DIR = os.path.join(ROOT, "data", "run")
LOG_DIR = os.path.join(ROOT, "data", "logs")


def venv_bin(name, exe):
    sub = ("Scripts", exe + ".exe") if os.name == "nt" else ("bin", exe)
    return os.path.join(ROOT, ".venvs", name, *sub)


def services(env):
    laya_host, laya_port = env.get("LAYA_HOST", "127.0.0.1"), env.get("LAYA_PORT", "8765")
    host, port = env.get("TRYON_HOST", "127.0.0.1"), env.get("TRYON_PORT", "7860")
    local = lambda h: "127.0.0.1" if h == "0.0.0.0" else h  # noqa: E731
    return [
        {"name": "laya", "cmd": [venv_bin("laya", "laya-serve")], "cwd": ROOT,
         "env": {"LAYA_DEVICE": env.get("LAYA_DEVICE", "cpu"), "LAYA_HOST": laya_host, "LAYA_PORT": laya_port},
         "health": f"http://{local(laya_host)}:{laya_port}/health"},
        {"name": "tryon", "cmd": [venv_bin("tryon", "python"), "-m", "uvicorn", "server:app", "--host", host, "--port", port],
         "cwd": os.path.join(ROOT, "app"), "env": {}, "health": f"http://{local(host)}:{port}/api/status",
         "url": f"http://{local(host)}:{port}"},
    ]


def pid_file(name):
    return os.path.join(RUN_DIR, f"{name}.pid")


def read_pid(name):
    try:
        with open(pid_file(name)) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def alive(pid):
    if pid is None:
        return False
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
        return str(pid) in out.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def get_json(url, timeout=2):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.load(r)
    except Exception:
        return None


def start(env, open_browser):
    os.makedirs(RUN_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    child_env = {**os.environ, **env}
    for svc in services(env):
        if alive(read_pid(svc["name"])):
            print(f"  {svc['name']} 已在运行（pid {read_pid(svc['name'])}）")
            continue
        if not os.path.isfile(svc["cmd"][0]):
            sys.exit(f"找不到 {svc['cmd'][0]}，请先运行 python scripts/setup.py")
        log = open(os.path.join(LOG_DIR, f"{svc['name']}.log"), "ab")
        kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS} if os.name == "nt" \
            else {"start_new_session": True}
        proc = subprocess.Popen(svc["cmd"], cwd=svc["cwd"], env={**child_env, **svc["env"]}, stdout=log, stderr=log,
                                stdin=subprocess.DEVNULL, **kwargs)
        with open(pid_file(svc["name"]), "w") as f:
            f.write(str(proc.pid))
        print(f"  {svc['name']} 已启动（pid {proc.pid}），日志 data/logs/{svc['name']}.log")

    print("  等待服务就绪（首次启动要加载模型，约 30–90 秒）…", flush=True)
    tryon = services(env)[1]
    deadline = time.time() + 600
    while time.time() < deadline:
        s = get_json(tryon["health"])
        if s and s.get("tryon") in ("ready", "disabled") and s.get("laya"):
            print(f"\n  就绪：{tryon['url']}")
            if open_browser:
                webbrowser.open(tryon["url"])
            return
        if s and s.get("tryon") == "error":
            sys.exit(f"换装模型加载失败：{s.get('tryon_error')}\n查看 data/logs/tryon.log")
        for svc in services(env):
            if not alive(read_pid(svc["name"])):
                sys.exit(f"{svc['name']} 进程退出了，查看 data/logs/{svc['name']}.log")
        time.sleep(3)
    sys.exit("等待超时，查看 data/logs/ 下的日志")


def stop(env):
    for svc in reversed(services(env)):
        pid = read_pid(svc["name"])
        if alive(pid):
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
            else:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            print(f"  {svc['name']} 已停止（pid {pid}）")
        else:
            print(f"  {svc['name']} 没有在运行")
        if os.path.exists(pid_file(svc["name"])):
            os.remove(pid_file(svc["name"]))


def status(env):
    for svc in services(env):
        pid = read_pid(svc["name"])
        health = get_json(svc["health"])
        state = "运行中" if alive(pid) else "未运行"
        print(f"  {svc['name']:6s} {state:4s} pid={pid}  健康检查：{json.dumps(health, ensure_ascii=False) if health else '无响应'}")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("start", "stop", "status", "restart"):
        sys.exit(__doc__)
    env = load_env()
    cmd = sys.argv[1]
    if cmd in ("stop", "restart"):
        stop(env)
    if cmd in ("start", "restart"):
        start(env, open_browser="--no-browser" not in sys.argv)
    if cmd == "status":
        status(env)


if __name__ == "__main__":
    main()
