# HTTP API

Default base URL: `http://127.0.0.1:7860`. Interactive docs at runtime: `/docs` (Swagger UI). Every error returns `{"detail": "reason (in Chinese)"}`.

User-facing strings returned by the API are in Chinese.

## Status

### `GET /api/status`

```json
{"tryon": "ready", "tryon_error": null, "laya": true}
```

Values of `tryon`: `idle` `loading` `ready` `error` `disabled` (`TRYON_ENGINE=off`).

## Wardrobe (garments)

| Method | Path | Description |
|---|---|---|
| GET | `/api/wardrobe` | All garments. Each item is a full `Listing` (see [Data model](data-model.md)), plus `category_label`, `url`, `url_back`, `capabilities` |
| POST | `/api/wardrobe` | Add one manually (multipart): `image` (front, required), `image_back`, `name`, `occasions`, `category` (`top` `outerwear` `pants` `skirt` `dress` `jumpsuit`). Returns `{"id"}` |
| DELETE | `/api/wardrobe/{id}` | Delete a garment |

## People

| Method | Path | Description |
|---|---|---|
| GET | `/api/persons` | Uploaded people first, then bundled samples. Each item has `id` `sample` `views` `trust` `issues` `warnings` `profile` `measured` |
| POST | `/api/person` | Create (multipart): `front` (required), `side`, `back`, `gender` (`female`/`male`), `height_cm`, `weight_kg` (required), `chest_cm` `waist_cm` `hip_cm` `shoulder_cm` `usual_top_size` `usual_bottom_size` (optional). If a photo fails the checks it returns **422**: `{"detail", "checks": {view: {passed, blocking[], warnings[]}}}` |
| PUT | `/api/person/{id}/profile` | Update body data (same fields, no photos); credibility is re-assessed. Bundled samples return 403 |
| DELETE | `/api/person/{id}` | Delete. Bundled samples return 403 |
| POST | `/api/prepare` | `{"person_id"}`: preprocess all views of this person in the background (called by the frontend when a person is selected) |

## Picking a garment (laya)

### `POST /api/choose`

```json
// request
{"text": "明天要去面试", "current_item": "mock_tee_white"}
// response
{"choice": "mock_blazer_beige", "matched_occasion": "面试、上班、正式场合",
 "probabilities": {"mock_blazer_beige": 0.61, "...": 0.05}, "confidence": 0.58,
 "model": "multilingual", "latency_ms": 212}
```

`current_item` is excluded from the candidates (used for "show me another one").

## Score

### `GET /api/score?person_id=&item_id=&mode=fast`

Estimated score before generation, returned per view (no `back` if the garment has no back image):

```json
{"front": {"view": "front", "overall": 88, "grade": "高",
  "visual": {"score": 87, "grade": "高", "deductions": [{"points": 10, "reason": "商品图是模拟生成的，不是真实商品照片"}]},
  "fit": {"score": 90, "grade": "高", "deductions": []},
  "plan": {"size": "L", "size_reason": "按你的胸围、腰围推荐 L 码", "length_cm": 116, "length_calibrated": true, "note": null},
  "qc": null, "checked": false, "qc_failures": [], "note": "…"}}
```

## Try-on

### `POST /api/tryon`

```json
{"person_id": "sample_fitted", "item_id": "mock_dress_floral", "view": "front", "mode": "fast", "seed": 42}
```

`view`: `front` `side` `back`; `mode`: `turbo` `fast` `quality`. Response:

```json
{"image": "data:image/jpeg;base64,…", "url": "/results/1790…jpg", "view": "front",
 "timing": {"prep_ms": 0, "total_ms": 7812, "steps": 10},
 "fit": {"size": "L", "length_cm": 116, "length_calibrated": true, "hem_y": 0.86, "…": "…"},
 "qc": {"length_diff_cm": 2.0},
 "score": {"…": "same as one view of /api/score, with checked=true"}}
```

Errors: 400 if the person has no photo for that view, 409 if the garment has no image for that view, 503 if the model is not ready.

### `POST /api/tryon/stream`

Same request. The response is line-delimited JSON (`application/x-ndjson`):

```
{"type": "preview", "step": 1, "total": 9, "view": "front", "image": "data:…", "elapsed_ms": 812}
{"type": "preview", "step": 3, …}
{"type": "done", …same as the /api/tryon response…}
```

On failure the last line is `{"type": "error", "detail": "…"}`.

## Turnaround video (requires a video model, see [Generation models](generation.md))

| Method | Path | Description |
|---|---|---|
| GET | `/api/video/config` | `{"available", "provider", "reason", "seconds"}`. When nothing is configured, `available=false` and `reason` explains how to configure it |
| POST | `/api/video` | `{"front_url", "back_url"}` (the `url` from try-on results), returns `{"request_id"}`. Returns **501** when no video model is configured |
| GET | `/api/video/{request_id}` | `{"status": "pending" \| "done" \| "failed", "url", "error"}`. When done, `url` is `/videos/…mp4` |

## Static files

`/catalog/…` garment images, `/samples/…` sample people, `/persons/…` uploaded people, `/results/…` try-on results, `/videos/…` turnaround videos, `/static/…` frontend files.
