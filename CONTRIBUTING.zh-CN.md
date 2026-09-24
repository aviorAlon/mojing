# 参与贡献

[English](CONTRIBUTING.md) | 简体中文

欢迎提 issue 和 pull request。

## 提 issue

- 问题：附上 `python scripts/doctor.py` 的输出、`data/logs/` 里相关的日志、操作系统和显卡型号。
- 换装效果问题：附上模特照片（请用虚构人物或你有权分享的照片）、商品图，以及页面上的可信度评分明细。

## 提 pull request

1. 从 `master` 拉分支，一个 PR 只做一件事。
2. 本地安装：`python scripts/setup.py --dev`。
3. 修改规则类逻辑（`validation.py`、`fitting.py`、`scoring.py`）时，同时补测试。
4. 提交前运行 `python -m pytest tests`，需要全部通过。改了换装管线的，再跑一次 `tests/e2e`，并在 PR 里附上改动前后的效果对比图。
5. 同时更新中英文两份文档（`docs/zh-CN/` 和 `docs/en/`）和两份更新日志。

## 原则

- **真实性优先**：宁可关闭功能或给出低分，也不用猜测的数据冒充真实数据。
- 不在仓库里放真人照片、有版权的商品图或模型权重。
- 面向用户的文字用中文；代码、注释、提交信息用英文。
