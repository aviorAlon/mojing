# 故障排查

先运行自检，大部分问题它都会直接给出处理方法：

```bash
python scripts/doctor.py
```

服务运行时的日志在 `data/logs/tryon.log` 和 `data/logs/laya.log`。

## 安装

**下载模型很慢或超时**
加上 `--hf-mirror` 走 hf-mirror.com；也可以在 `.env` 里设置 `HF_ENDPOINT`。下载失败后重新运行 `python scripts/setup.py --only models` 会接着下载。设置 `HF_TOKEN` 可以提高限速。

**`pip install` 失败 / 找不到 torch 版本**
检查网络，或者给 pip 配置镜像：`pip config set global.index-url <镜像>`。torch 的 CUDA 版固定从 `download.pytorch.org/whl/cu124` 下载，内网环境需要为它单独配置代理。

**没有检测到显卡**
`nvidia-smi` 必须能在命令行里运行。装好驱动后删掉 `.venvs/tryon`，再重新运行 `setup.py`。

## 启动

**`run.py start` 报"进程退出了"**
查看 `data/logs/<服务名>.log` 的最后几行。常见原因：
- 端口被占用：在 `.env` 里换 `TRYON_PORT` / `LAYA_PORT`。
- 显存不足（`CUDA out of memory`）：关掉占用显卡的程序，或者先 `run.py stop` 再启动，避免同时跑两份。

**一直在"等待服务就绪"**
首次启动要加载模型，并预处理衣柜和示例模特，通常 30–90 秒。laya 第一次启动时如果没有提前预热，还会下载约 3GB 的模型。

**日志里有 `onnxruntime ... cublasLt64_13.dll which is missing`**
姿态检测组件想用 CUDA 13，本机没有，于是自动回退到 CPU。只影响每张新照片第一次预处理的速度（约 1 秒），可以忽略。

## 使用

**看不到可信度评分 / 界面没有更新**
页面引用的 JS 和 CSS 带了版本号，正常情况下刷新就是最新的。仍然不对时，按 Ctrl+F5 强制刷新。

**上传照片被拦截**
按照片上的红字提示重拍。最常见的原因：头顶或脚被裁掉、把正面照放进了背面位置、画面里有多个人。

**换装结果显示"质检未通过"**
说明生成结果和尺码表或原照片对不上，例如衣长明显偏短、腿被画细了。可以换"精细"档，或者换一件衣服再试。原图里被遮住的身体部位只能靠推测，用贴身短袖 + 短裤的照片效果最好。

**laya 选的衣服不对**
laya 靠商品的 `occasions`（适合场合）来匹配需求。把场合写成简短、具体的短语效果最好，例如"面试、上班、正式"，长句子描述的效果会差很多。

**点"生成转身视频"提示未配置 / 工具报"未配置图片生成模型"**
这些是可选功能，需要接入你自己的模型，见 [生成模型配置](generation.md)。改完 `.env` 后执行 `python scripts/run.py restart`。
