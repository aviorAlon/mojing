# 开发指南

## 环境

```bash
python scripts/setup.py --dev      # 额外安装 pytest、playwright + Chromium
```

开发时可以直接前台运行后端，改完代码手动重启：

```bash
cd app
../.venvs/tryon/bin/python -m uvicorn server:app --port 7860          # Windows: ..\.venvs\tryon\Scripts\python
```

laya 服务仍然用 `python scripts/run.py start` 启动，或者单独执行 `.venvs/laya/bin/laya-serve`（需要设置 `LAYA_PORT=8765`）。

只改界面或 API、不需要真的换装时，设置 `TRYON_ENGINE=off` 跳过模型加载，没有 GPU 的机器也能开发。

## 测试

```bash
.venvs/tryon/bin/python -m pytest tests               # 单元测试 + API 测试，无需 GPU，约 5 秒
python scripts/run.py start --no-browser
.venvs/tryon/bin/python -m pytest tests/e2e           # 浏览器端到端测试，需要服务已就绪
```

| 文件 | 覆盖内容 |
|---|---|
| `tests/test_validation.py` | 身材数据范围、BMI、围度关系、与照片交叉比对、可信度等级 |
| `tests/test_fitting.py` | 挑尺码（围度、弹力、常穿尺码、中间码）、衣长计划、手臂遮挡规则 |
| `tests/test_scoring.py` | 扣分规则、质检一票否决 |
| `tests/test_data.py` | 内置商品和示例模特的数据完整性 |
| `tests/test_api.py` | HTTP 接口（使用临时数据目录，`TRYON_ENGINE=off`） |
| `tests/e2e/test_ui.py` | 真实浏览器里完成三视角换装，检查评分和缺数据的视角 |

## 代码结构

| 模块 | 职责 | 依赖 GPU |
|---|---|---|
| `app/config.py` | 读取环境变量 | 否 |
| `app/models.py` | 数据模型 | 否 |
| `app/validation.py` | 照片检查、身材可信度 | 否（输入是预先分析好的结果） |
| `app/fitting.py` | 尺码与衣长 | 否 |
| `app/scoring.py` | 可信度评分 | 否 |
| `app/tryon.py` | 模型加载、遮挡区域、采样、质检 | 是 |
| `app/server.py` | HTTP 层，把以上模块串起来 | 间接 |

规则类的逻辑（validation、fitting、scoring）都是纯函数，方便单测。新规则请同时加测试。

## 添加内置商品

在 `catalog/<id>/` 放 `listing.json`、`front.jpg`，有背面图就放 `back.jpg`。`listing.json` 的格式参考现有商品和 [数据模型](data-model.md)。加完运行 `pytest tests/test_data.py` 检查。

也可以用配置好的图片模型批量生成，见 [生成模型配置](generation.md#生成模拟商品)。

## 添加内置示例模特

在 `samples/persons/<id>/` 放 `front.jpg`（侧面、背面可选）和 `profile.json`。最简单的做法：通过网页"新建模特"上传，这样照片会先经过检查，然后把 `data/persons/<新id>/` 拷到 `samples/persons/<id>/`，并把 `profile.json` 里的 `id` 改成目录名。id 只能包含小写字母、数字和下划线。

示例模特只能用虚构人物（AI 生成），不要放真人照片。

## 约定

- 面向用户的文字用中文；代码、注释、提交信息用英文。
- 代码不写多余注释，只在"为什么这么做"不明显时写一行。
- 缺数据时关闭对应功能并说明原因，不要用猜测值填补。
