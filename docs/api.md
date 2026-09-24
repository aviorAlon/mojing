# HTTP API

基地址默认 `http://127.0.0.1:7860`。运行时的交互式文档：`/docs`（Swagger UI）。所有错误都返回 `{"detail": "中文原因"}`。

## 状态

### `GET /api/status`

```json
{"tryon": "ready", "tryon_error": null, "laya": true}
```

`tryon` 的取值：`idle` `loading` `ready` `error` `disabled`（`TRYON_ENGINE=off`）。

## 衣柜（商品）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/wardrobe` | 所有商品。每项是完整的 `Listing`（见 [数据模型](data-model.md)），外加 `category_label`、`url`、`url_back`、`capabilities` |
| POST | `/api/wardrobe` | 手动添加（multipart）：`image`（正面，必填）、`image_back`、`name`、`occasions`、`category`（`top` `outerwear` `pants` `skirt` `dress` `jumpsuit`）。返回 `{"id"}` |
| DELETE | `/api/wardrobe/{id}` | 删除商品 |

## 模特

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/persons` | 用户上传的在前，内置示例在后。每项包含 `id` `sample` `views` `trust` `issues` `warnings` `profile` `measured` |
| POST | `/api/person` | 新建（multipart）：`front`（必填）、`side`、`back`、`gender`（`female`/`male`）、`height_cm`、`weight_kg`（必填）、`chest_cm` `waist_cm` `hip_cm` `shoulder_cm` `usual_top_size` `usual_bottom_size`（选填）。照片没通过检查时返回 **422**：`{"detail", "checks": {view: {passed, blocking[], warnings[]}}}` |
| PUT | `/api/person/{id}/profile` | 修改身材资料（字段同上，不含照片），会重新评估可信度；内置示例返回 403 |
| DELETE | `/api/person/{id}` | 删除；内置示例返回 403 |
| POST | `/api/prepare` | `{"person_id"}`，在后台预处理这个模特的所有视角（选中模特时由前端调用） |

## 挑衣服（laya）

### `POST /api/choose`

```json
// 请求
{"text": "明天要去面试", "current_item": "mock_tee_white"}
// 响应
{"choice": "mock_blazer_beige", "matched_occasion": "面试、上班、正式场合",
 "probabilities": {"mock_blazer_beige": 0.61, "...": 0.05}, "confidence": 0.58,
 "model": "multilingual", "latency_ms": 212}
```

`current_item` 会被排除在候选之外（用于"换一件"）。

## 评分

### `GET /api/score?person_id=&item_id=&mode=fast`

生成前的预估评分。按视角返回（商品没有背面图时不含 `back`）：

```json
{"front": {"view": "front", "overall": 88, "grade": "高",
  "visual": {"score": 87, "grade": "高", "deductions": [{"points": 10, "reason": "商品图是模拟生成的，不是真实商品照片"}]},
  "fit": {"score": 90, "grade": "高", "deductions": []},
  "plan": {"size": "L", "size_reason": "按你的胸围、腰围推荐 L 码", "length_cm": 116, "length_calibrated": true, "note": null},
  "qc": null, "checked": false, "qc_failures": [], "note": "…"}}
```

## 换装

### `POST /api/tryon`

```json
{"person_id": "sample_fitted", "item_id": "mock_dress_floral", "view": "front", "mode": "fast", "seed": 42}
```

`view`：`front` `side` `back`；`mode`：`turbo` `fast` `quality`。响应：

```json
{"image": "data:image/jpeg;base64,…", "url": "/results/1790…jpg", "view": "front",
 "timing": {"prep_ms": 0, "total_ms": 7812, "steps": 10},
 "fit": {"size": "L", "length_cm": 116, "length_calibrated": true, "hem_y": 0.86, "…": "…"},
 "qc": {"length_diff_cm": 2.0},
 "score": {"…": "同 /api/score 单个视角，checked=true"}}
```

错误：模特没有该视角 400，商品没有该视角的图 409，模型未就绪 503。

### `POST /api/tryon/stream`

请求同上。响应是逐行 JSON（`application/x-ndjson`）：

```
{"type": "preview", "step": 1, "total": 9, "view": "front", "image": "data:…", "elapsed_ms": 812}
{"type": "preview", "step": 3, …}
{"type": "done", …和 /api/tryon 的响应一样…}
```

出错时最后一行是 `{"type": "error", "detail": "…"}`。

## 转身视频（需要配置视频模型，见 [生成模型配置](generation.md)）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/video/config` | `{"available", "provider", "reason", "seconds"}`，没配置时 `available=false`，`reason` 说明怎么配 |
| POST | `/api/video` | `{"front_url", "back_url"}`（换装结果里的 `url`），返回 `{"request_id"}`。没配置视频模型时返回 **501** |
| GET | `/api/video/{request_id}` | `{"status": "pending" \| "done" \| "failed", "url", "error"}`，完成后 `url` 是 `/videos/…mp4` |

## 静态资源

`/catalog/…` 商品图，`/samples/…` 示例模特，`/persons/…` 上传的模特，`/results/…` 换装结果，`/videos/…` 转身视频，`/static/…` 前端文件。
