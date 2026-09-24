# Data model

Defined in `app/models.py` (pydantic). Core principle: **every value records where it came from; missing data stays missing, and features that depend on it are switched off or flagged — never filled with made-up values.**

## Field source `Val`

```json
{"value": "微弹", "source": "platform", "confidence": null, "note": null}
```

| source | Meaning | Examples |
|---|---|---|
| `platform` | Structured field from the e-commerce platform, stored as-is | Price, SKUs, product attributes |
| `extracted` | Recognised from the platform's images or copy; must carry `confidence` | OCR of a size-chart image on the detail page, copy such as "model is 168 cm" |
| `user_input` | Entered by the user | Height, weight |
| `measured` | Measured from the user's photos | Shoulder width relative to height |
| `derived` | Computed from the above | Recommended size, hem position |
| `mock` | Mock data (testing only) | Every garment in `catalog/` |
| `missing` | No data | — |

The UI shows a source tag next to each garment attribute.

## Garment `Listing`

One product on an e-commerce platform, stored at `catalog/<id>/listing.json` with its images in the same folder.

| Field | Description |
|---|---|
| `id`, `platform`, `item_id`, `url`, `fetched_at` | Provenance |
| `title`, `brand`, `price` | Basic info |
| `category_path` | The platform's original category path, e.g. `["女装", "连衣裙"]` |
| `category` | Normalised category: `top` `outerwear` `pants` `skirt` `dress` `jumpsuit` |
| `gender` | Target gender |
| `images[]` | `file`, `kind` (`flat_lay` / `hanging` / `on_model` / `detail`), `view` (`front` / `back` / `side`), `source` |
| `skus[]` | Colour, size, stock |
| `attributes` | The platform's "product parameters": `material` `thickness` `stretch` `fit` `length_type` `sleeve` `neckline` `season` `style`, each a `Val` |
| `size_chart` | `basis` (`garment` = flat garment measurements / `body` = body measurements the size fits — **never mix the two**), `rows[]` (size → `length` `chest` `shoulder` `sleeve` `waist` `hip` etc., in cm), `source`, `confidence` |
| `model_reference` | "Model is 168 cm, 48 kg, wearing size S" |
| `occasions` | Occasion phrases laya matches requests against, e.g. "面试、上班、得体" (interview, office, polished) |
| `raw` | The platform's raw response, kept in full for traceability |

### Capabilities (`Listing.capabilities()`)

Which features are available depends on how complete the data is:

| Capability | Requires | When missing |
|---|---|---|
| `tryon_front` | Front garment image | Cannot be listed |
| `tryon_back` | Back garment image | No back view is generated; the back tab shows why |
| `size_recommend` | Size chart | Only the size list is shown, no recommendation |
| `length_mark` | Garment length in the size chart | Length is not set from the size chart; the score is reduced |
| `fit_hint` | Size chart + stretch attribute | No tightness hint |

### Connecting real e-commerce data

We suggest writing a "platform adapter" that converts responses from platform APIs (affiliate / promotion APIs such as Taobao Union, JD Union, Duoduo Jinbao, Douyin Selected Alliance) into `Listing`:

1. Map the platform's structured fields directly, with `source="platform"`.
2. Normalise the category path to the 6 `category` values above; don't list products that can't be mapped.
3. Classify main and detail images into flat-lay / on-model / detail and front / back; classification carries a confidence, and low-confidence images should not be used for try-on.
4. Size charts often exist only as images and need OCR: `source="extracted"` with a confidence. The score deducts points for low-confidence size charts.
5. `occasions` can be generated from attributes such as category, style and season (`source="derived"`); laya relies on it to match requests.
6. Put the platform's raw data in `raw` in full.

## Person `Person`

Uploaded people live in `data/persons/<id>/`, bundled samples in `samples/persons/<id>/` (read-only). Each folder has `front.jpg`, `side.jpg`, `back.jpg` (side and back optional) and `profile.json`.

| Field | Description |
|---|---|
| `views` | View → file name |
| `photo_checks` | Per-photo check result: `passed`, `blocking[]` (reasons for rejection), `warnings[]` (hints), `metrics` (measurements) |
| `profile` | `BodyProfile`: gender, height, weight (required); chest / waist / hip, shoulder width, usual sizes (optional); all `Val` (`user_input`) |
| `measured` | Measurements from photos: shoulder width, hip width, leg-length ratio (`measured`; used only for cross-checking, never replaces what the user entered) |
| `trust` | `trusted` / `suspicious` / `untrusted` / `unverified` |
| `issues[]` | Credibility issues: `level`, `field`, `message` |
| `version`, `updated_at` | Profile version, incremented when the profile is edited |

Photo preprocessing results (pose, parsing, masks) are cached in memory by the try-on service, so a person uploaded once can be reused indefinitely.
