# plugins/

把你自己的生成模型实现放在这个目录，然后在 `.env` 里指向它：

```ini
IMAGE_PROVIDER=my_image:MyImageProvider     # 可选：不用 OpenAI 兼容接口时
VIDEO_PROVIDER=my_video:MyVideoProvider     # 转身视频
```

`plugins/` 会自动加入导入路径，所以 `my_video:MyVideoProvider` 对应 `plugins/my_video.py` 里的 `MyVideoProvider` 类。
这个目录下除本文件外的内容不会被提交（见 `.gitignore`），可以放心写入 API key 相关的代码。

接口定义和完整示例见 [docs/generation.md](../docs/generation.md)。
