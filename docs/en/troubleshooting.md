# Troubleshooting

Run the self-check first; for most problems it tells you what to do directly:

```bash
python scripts/doctor.py
```

Service logs are in `data/logs/tryon.log` and `data/logs/laya.log`.

## Installation

**Model downloads are slow or time out**
Add `--hf-mirror` to go through hf-mirror.com, or set `HF_ENDPOINT` in `.env`. If a download fails, rerun `python scripts/setup.py --only models` to resume. Setting `HF_TOKEN` raises the rate limit.

**`pip install` fails / torch version not found**
Check your network, or point pip at a mirror: `pip config set global.index-url <mirror>`. The CUDA build of torch is always downloaded from `download.pytorch.org/whl/cu124`; on an internal network you need to configure a proxy for it separately.

**No GPU detected**
`nvidia-smi` must run from the command line. After installing the driver, delete `.venvs/tryon` and rerun `setup.py`.

## Startup

**`run.py start` reports "process exited" (进程退出了)**
Check the last lines of `data/logs/<service>.log`. Common causes:
- Port in use: change `TRYON_PORT` / `LAYA_PORT` in `.env`.
- Out of GPU memory (`CUDA out of memory`): close programs using the GPU, or run `run.py stop` before starting so two copies aren't running at once.

**Stuck at "waiting for services to be ready" (等待服务就绪)**
The first start loads the models and preprocesses the wardrobe and sample people, usually 30–90 seconds. If laya was not pre-warmed, its first start also downloads about 3GB of models.

**The log contains `onnxruntime ... cublasLt64_13.dll which is missing`**
The pose detector tries to use CUDA 13, which isn't installed, so it falls back to CPU automatically. This only affects the first preprocessing of each new photo (about 1 second) and can be ignored.

## Usage

**Reliability score not showing / UI not updated**
The page references its JS and CSS with a version number, so a normal refresh gets the latest. If it's still wrong, force-refresh with Ctrl+F5.

**Photo upload rejected**
Retake the photo following the red message on it. The most common causes: the top of the head or the feet are cropped, a front photo was put in the back slot, or more than one person is in the frame.

**Try-on result shows "quality check failed" (质检未通过)**
The result doesn't match the size chart or the original photo, e.g. the garment is clearly too short or the legs were drawn thinner. Try the "Fine" (精细) mode or a different garment. Body parts hidden in the original photo can only be guessed; photos in a fitted T-shirt and shorts work best.

**laya picks the wrong garment**
laya matches requests against each garment's `occasions` (suitable occasions). Short, specific phrases work best, e.g. "面试、上班、正式" (interview, office, formal); long sentences work much worse.

**"Generate turnaround video" (生成转身视频) says it's not configured / a tool reports "image generation model not configured" (未配置图片生成模型)**
These are optional features that need your own models; see [Generation models](generation.md). After editing `.env`, run `python scripts/run.py restart`.
