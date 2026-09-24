# 部署指南

## 硬件与系统要求

| 项目 | 最低 | 推荐 | 说明 |
|---|---|---|---|
| GPU | NVIDIA，8GB 显存 | 12GB 以上，或数据中心卡（A10/A100/H100） | 换装模型推理约占 4GB；和桌面程序、浏览器共用显卡时要留余量 |
| 内存 | 16GB | 32GB | laya 预加载 3 个 checkpoint 约占 3–4GB |
| 磁盘 | 15GB | 30GB | 两个虚拟环境约 7GB，FASHN 权重约 2GB，laya 模型约 3GB |
| Python | 3.10 | 3.11 | 只需要一个系统 Python 来运行安装脚本 |
| 系统 | Windows 10/11、Linux x86_64 | — | 已在 Windows 10 + RTX 4060 上完整验证；Linux 使用同一套脚本 |

不同显卡的参考耗时（标准档 10 步，每个视角）：RTX 4060 约 8 秒；RTX 4090 预计约 3 秒；H100 预计 1–2 秒。后两者是按 FASHN 官方数据（H100 上 30 步约 5 秒）估算的，未实测。

没有 NVIDIA 显卡时，`setup.py` 会自动安装 CPU 版 torch，网站可以正常打开和操作，但每个视角的换装要几分钟，只适合调试界面。

## 安装

```bash
python scripts/setup.py [选项]
```

| 选项 | 作用 |
|---|---|
| （无） | 全部安装：虚拟环境、依赖、模型权重，最后运行自检 |
| `--hf-mirror` | 通过 `https://hf-mirror.com` 下载模型（中国大陆网络） |
| `--cpu` | 强制安装 CPU 版 torch |
| `--dev` | 额外安装 pytest、playwright 和 Chromium（跑测试用） |
| `--skip-models` | 只装依赖，不下载模型 |
| `--only tryon\|laya\|models` | 只执行某一步（例如重新下载模型：`--only models`） |

安装脚本做的事情：

1. 在 `.venvs/tryon` 创建换装服务的虚拟环境：检测到 NVIDIA 显卡就安装 CUDA 12.4 版 torch 2.6，然后安装 `requirements/tryon.txt`（其中 FASHN VTON 固定到经过验证的 commit）。
2. 在 `.venvs/laya` 创建决策服务的虚拟环境：CPU 版 torch 2.14 + laya 0.3.20。laya 和换装服务依赖的 torch 版本不兼容，所以两者必须分开。
3. 下载 FASHN VTON v1.5 权重到 `models/fashn/`，DWPose 姿态模型放在 `models/fashn/dwpose/`，人体解析模型放在 Hugging Face 缓存。
4. 预热 laya 模型（3 个 checkpoint 打包在一个 Hugging Face 仓库里，下载到缓存）。
5. 从 `.env.example` 生成 `.env`。
6. 运行 `scripts/doctor.py` 自检。

每一步都可以重复执行，已完成的部分会跳过或快速通过。

### 离线 / 内网安装

在能联网的机器上执行一次 `setup.py`，然后把以下内容拷到目标机器的同一位置：

- `models/fashn/`
- Hugging Face 缓存目录（默认 `~/.cache/huggingface/hub`，Windows 是 `%USERPROFILE%\.cache\huggingface\hub`），其中包含 laya 模型和人体解析模型
- 目标机器上的 pip 可以指向内网镜像：`pip config set global.index-url <镜像地址>`

然后在目标机器上运行 `python scripts/setup.py`。已有的模型文件会被跳过。

## 启动与停止

```bash
python scripts/run.py start            # 后台启动两个服务，等待就绪后打开浏览器（--no-browser 不打开）
python scripts/run.py status           # 查看进程和健康检查
python scripts/run.py stop
python scripts/run.py restart
```

- laya 决策服务：默认 `127.0.0.1:8765`
- 换装网站：默认 `127.0.0.1:7860`
- 日志：`data/logs/laya.log`、`data/logs/tryon.log`
- 首次启动要加载模型并预处理衣柜和示例模特，大约需要 30–90 秒

## 配置

所有配置都在 `.env` 里（完整说明见 `.env.example`）。环境变量的优先级高于 `.env`。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `TRYON_HOST` / `TRYON_PORT` | `127.0.0.1` / `7860` | 网站监听地址 |
| `TRYON_ENGINE` | `on` | `off` 表示不加载换装模型，只跑界面和 API（无 GPU 调试用） |
| `FASHN_WEIGHTS` | `models/fashn` | FASHN 权重目录 |
| `LAYA_HOST` / `LAYA_PORT` | `127.0.0.1` / `8765` | laya 服务地址 |
| `LAYA_DEVICE` | `cpu` | 放到 GPU 上会和换装模型抢显存，没有必要 |
| `DATA_DIR` | `data` | 上传的人物、结果、视频、日志 |
| `CATALOG_DIR` | `catalog` | 商品目录 |
| `SAMPLES_DIR` | `samples/persons` | 内置示例模特 |
| `HF_ENDPOINT` | — | Hugging Face 镜像地址 |
| `IMAGE_API_BASE` / `IMAGE_API_KEY` / `IMAGE_MODEL` / `IMAGE_PROVIDER` | 未配置 | 图片生成模型（模拟商品、模拟模特），见 [生成模型配置](generation.md) |
| `VIDEO_PROVIDER` / `VIDEO_SECONDS` | 未配置 / `5` | 视频生成模型（转身视频），见 [生成模型配置](generation.md) |

## 局域网访问

在 `.env` 里设置 `TRYON_HOST=0.0.0.0`，然后执行 `run.py restart`，同一网络里的设备就能通过 `http://<本机IP>:7860` 访问。

> **注意**：网站**没有登录和权限控制**，任何能访问的人都能上传照片、查看其他人上传的模特。只在可信网络里这样使用；对公网开放前，请在前面加一层带认证的反向代理（例如 Nginx + Basic Auth 或单点登录）。

laya 服务不需要对外开放，保持 `LAYA_HOST=127.0.0.1` 即可。

## Linux 服务器 / 云 GPU

```bash
sudo apt install -y python3 python3-venv git   # Ubuntu / Debian
git clone <this repo> /opt/laya-tryon && cd /opt/laya-tryon
python3 scripts/setup.py
python3 scripts/run.py start --no-browser
```

需要确认 `nvidia-smi` 能正常输出（已安装 NVIDIA 驱动）。CUDA toolkit 不需要单独安装，torch 的 wheel 自带 CUDA 运行时。

### 用 systemd 常驻

`/etc/systemd/system/laya-tryon.service`：

```ini
[Unit]
Description=Laya TryOn
After=network-online.target

[Service]
Type=forking
User=tryon
WorkingDirectory=/opt/laya-tryon
ExecStart=/usr/bin/python3 scripts/run.py start --no-browser
ExecStop=/usr/bin/python3 scripts/run.py stop
Restart=on-failure
TimeoutStartSec=600

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now laya-tryon
```

### Windows 开机自启

用"任务计划程序"新建一个任务：触发器选"登录时"，操作填 `python`，参数填 `scripts\run.py start --no-browser`，起始于填项目目录。

## 升级

```bash
git pull
python scripts/setup.py        # 依赖有变化时会自动更新，已下载的模型不会重复下载
python scripts/run.py restart
```

## 卸载

停止服务后删除项目目录即可。如果还想清掉模型缓存，删除 Hugging Face 缓存里的 `models--convaiinnovations--*` 和 `models--fashn-ai--*`。
