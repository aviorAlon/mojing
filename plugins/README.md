# plugins/

English | [简体中文](#简体中文)

Put your own generation model implementations in this directory and point `.env` at them:

```ini
IMAGE_PROVIDER=my_image:MyImageProvider     # optional, instead of an OpenAI-compatible API
VIDEO_PROVIDER=my_video:MyVideoProvider     # turnaround videos
```

`plugins/` is added to the import path automatically, so `my_video:MyVideoProvider` means class `MyVideoProvider` in `plugins/my_video.py`.
Everything in this directory except this file is ignored by git (see `.gitignore`), so it is safe to read API keys here.

Interfaces and full examples: [docs/en/generation.md](../docs/en/generation.md).

---

## 简体中文

把你自己的生成模型实现放在这个目录，然后在 `.env` 里指向它：

```ini
IMAGE_PROVIDER=my_image:MyImageProvider     # 可选：不用 OpenAI 兼容接口时
VIDEO_PROVIDER=my_video:MyVideoProvider     # 转身视频
```

`plugins/` 会自动加入导入路径，所以 `my_video:MyVideoProvider` 对应 `plugins/my_video.py` 里的 `MyVideoProvider` 类。
这个目录下除本文件外的内容不会被提交（见 `.gitignore`），可以放心在这里读取 API key。

接口定义和完整示例见 [docs/zh-CN/generation.md](../docs/zh-CN/generation.md)。
