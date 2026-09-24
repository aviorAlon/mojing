# 生成模型配置（可选）

项目里有三处需要"生成"能力，都**默认不配置**，由你接入自己的模型：

| 用途 | 入口 | 需要的配置 |
|---|---|---|
| 生成模拟商品（平铺图正面 + 背面） | `tools/generate_catalog.py` | 图片模型 |
| 生成模拟模特（正 / 侧 / 背三视图） | `tools/generate_person.py` | 图片模型 |
| 网站上的"生成转身视频" | 换装结果下方的按钮 | 视频模型 |

没有配置时，这些入口会直接报错，并提示需要设置哪些变量。换装本身不依赖它们。仓库里自带的 demo 商品和两位示例模特可以直接使用。

## 图片模型

### 方式一：OpenAI 兼容的 Images API（内置）

在 `.env` 里设置：

```ini
IMAGE_API_BASE=https://api.openai.com/v1     # 任何兼容 OpenAI Images API 的服务
IMAGE_API_KEY=sk-...
IMAGE_MODEL=gpt-image-1
IMAGE_SIZE=1024x1536                         # 竖版，适合衣服和全身照
```

调用方式：

- 没有参考图时：`POST {IMAGE_API_BASE}/images/generations`，JSON 格式 `{"model", "prompt", "size", "n": 1}`。
- 有参考图时：`POST {IMAGE_API_BASE}/images/edits`，multipart 格式，字段为 `image`、`model`、`prompt`、`size`。生成衣服背面、模特侧面和背面时会用到，目的是保证和正面是同一件衣服、同一个人。
- 返回 `data[0].b64_json` 或 `data[0].url` 都可以。

### 方式二：自己的实现

在 `plugins/` 下写一个类，然后设置 `IMAGE_PROVIDER=模块名:类名`：

```python
# plugins/my_image.py
class MyImageProvider:
    name = "my-image-model"

    def generate(self, prompt: str, reference: bytes | None = None) -> bytes:
        """返回 PNG/JPEG 字节。有 reference 时，保持参考图里的主体（同一件衣服 / 同一个人），按 prompt 生成新视角。"""
        ...
```

```ini
IMAGE_PROVIDER=my_image:MyImageProvider
```

`IMAGE_PROVIDER` 的优先级高于 `IMAGE_API_KEY`。

## 视频模型

视频生成接口各家差异很大，所以只提供插件方式。在 `plugins/` 下实现：

```python
# plugins/my_video.py
import os
import httpx


class MyVideoProvider:
    name = "my-video-model"

    def __init__(self):
        self.key = os.environ["MY_VIDEO_KEY"]          # 自己的配置写进 .env 即可

    def submit(self, prompt: str, first_frame: bytes, last_frame: bytes | None, seconds: int) -> str:
        """提交任务，返回任务 id。
        first_frame：正面换装结果（JPEG）；last_frame：背面换装结果，没有背面时为 None。
        有首尾帧时 prompt 描述"从正面转到背面"，只有首帧时描述"原地转一圈"。"""
        r = httpx.post("https://video.example.com/v1/jobs", headers={"Authorization": f"Bearer {self.key}"},
                       files={"first_frame": first_frame, **({"last_frame": last_frame} if last_frame else {})},
                       data={"prompt": prompt, "duration": seconds})
        r.raise_for_status()
        return r.json()["id"]

    def poll(self, job_id: str) -> dict:
        """返回 {"status": "pending"} / {"status": "done", "video": mp4 字节} / {"status": "failed", "error": "原因"}。"""
        job = httpx.get(f"https://video.example.com/v1/jobs/{job_id}", headers={"Authorization": f"Bearer {self.key}"}).json()
        if job["state"] == "succeeded":
            return {"status": "done", "video": httpx.get(job["video_url"]).content}
        if job["state"] == "failed":
            return {"status": "failed", "error": job.get("error")}
        return {"status": "pending"}
```

```ini
VIDEO_PROVIDER=my_video:MyVideoProvider
VIDEO_SECONDS=5
```

上面的 URL 和字段只是示意，请换成你所用服务的实际接口。网站每 5 秒轮询一次 `poll`，拿到视频后保存到 `data/videos/`。改完配置后执行 `python scripts/run.py restart`。

`plugins/` 目录下除 `README.md` 外的文件都不会提交到 git，可以放心在里面读取密钥。

## 生成模拟商品

商品的定义写在 `tools/catalog_spec.json`：标题、类目、价格、属性、尺码表、模特参考、适合场合，以及正面和背面的外观描述。按这个格式加一项，然后：

```bash
.venvs/tryon/bin/python tools/generate_catalog.py                          # 生成 catalog/ 里还没有的商品
.venvs/tryon/bin/python tools/generate_catalog.py --only my_item --force   # 重新生成某一件
.venvs/tryon/bin/python tools/generate_catalog.py --spec my.json --out other_catalog/
```

每件商品先生成正面平铺图，再用它作参考生成背面，保证正反面是同一件衣服。所有字段都会标注 `source="mock"`。

## 生成模拟模特

```bash
.venvs/tryon/bin/python tools/generate_person.py --out samples/persons/sample_new \
    --gender female --height 165 --weight 55 --look "大约30岁的普通中国女性，中等身材，黑色低马尾"

# 生成后直接注册到正在运行的网站：会经过和用户上传完全一样的照片检查和可信度评估
.venvs/tryon/bin/python tools/generate_person.py --out /tmp/p1 --gender male --height 175 --weight 70 \
    --look "大约35岁的普通中国男性，偏瘦，短发" --register http://127.0.0.1:7860
```

按照上传要求，生成的人物都穿贴身短袖 + 短裤。先生成正面，再以正面为参考生成侧面和背面。只描述虚构人物，不要用来生成真实存在的人。

要把生成结果放进 `samples/persons/` 作为内置示例：先用 `--register` 注册到网站，然后按 [开发指南](development.md#添加内置示例模特) 把 `data/persons/<id>/` 拷过去。
