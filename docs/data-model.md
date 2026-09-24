# 数据模型

定义在 `app/models.py`（pydantic）。核心原则：**每个值都记录来源；缺数据就保持缺失，依赖它的功能关闭或提示，绝不补造。**

## 字段来源 `Val`

```json
{"value": "微弹", "source": "platform", "confidence": null, "note": null}
```

| source | 含义 | 例子 |
|---|---|---|
| `platform` | 电商平台的结构化字段，原样保存 | 价格、SKU、商品属性 |
| `extracted` | 从平台的图片或文案里识别出来，必须带 `confidence` | 详情页尺码表图片 OCR、"模特身高 168" 这类文案 |
| `user_input` | 用户填写 | 身高、体重 |
| `measured` | 从用户照片测量 | 肩宽和身高的比例 |
| `derived` | 由以上数据计算得出 | 推荐尺码、下摆位置 |
| `mock` | 模拟数据（仅测试用） | `catalog/` 里的全部商品 |
| `missing` | 没有数据 | — |

页面上每个商品属性旁都会显示来源标签。

## 商品 `Listing`

对应电商平台的一个商品，存放在 `catalog/<id>/listing.json`，图片放在同一目录下。

| 字段 | 说明 |
|---|---|
| `id`、`platform`、`item_id`、`url`、`fetched_at` | 来源信息 |
| `title`、`brand`、`price` | 基本信息 |
| `category_path` | 平台原始类目路径，例如 `["女装", "连衣裙"]` |
| `category` | 归一化类目：`top` `outerwear` `pants` `skirt` `dress` `jumpsuit` |
| `gender` | 适用性别 |
| `images[]` | `file`、`kind`（`flat_lay` 平铺 / `hanging` 挂拍 / `on_model` 模特图 / `detail` 细节）、`view`（`front` / `back` / `side`）、`source` |
| `skus[]` | 颜色、尺码、库存 |
| `attributes` | 平台"商品参数"：`material` `thickness` `stretch` `fit` `length_type` `sleeve` `neckline` `season` `style`，每个都是 `Val` |
| `size_chart` | `basis`（`garment` 成衣尺寸 / `body` 适穿人体尺寸，**两者不能混用**）、`rows[]`（尺码 → `length` `chest` `shoulder` `sleeve` `waist` `hip` 等，单位 cm）、`source`、`confidence` |
| `model_reference` | "模特身高 168 体重 48 穿 S 码" |
| `occasions` | laya 用来匹配需求的场合短语，例如"面试、上班、得体" |
| `raw` | 平台原始返回数据，完整保留以便追溯 |

### 能力（`Listing.capabilities()`）

根据数据完整度决定哪些功能可用：

| 能力 | 需要 | 缺失时 |
|---|---|---|
| `tryon_front` | 正面商品图 | 不能上架 |
| `tryon_back` | 背面商品图 | 不生成背面，背面标签显示原因 |
| `size_recommend` | 尺码表 | 只显示尺码列表，不推荐 |
| `length_mark` | 尺码表里有衣长 | 不按尺码表定长，评分扣分 |
| `fit_hint` | 尺码表 + 弹力属性 | 不提示松紧 |

### 接入真实电商数据

建议写一个"平台适配器"，把平台接口（淘宝联盟、京东联盟、多多进宝、抖音精选联盟等推广 API）的返回转换成 `Listing`：

1. 平台结构化字段直接映射，`source="platform"`。
2. 类目路径归一化到上面 6 个 `category`，映射不了的商品先不上架。
3. 主图、详情图用图像分类区分平铺 / 模特 / 细节和正 / 背面；分类结果带置信度，低置信度的图不要用来换装。
4. 尺码表往往只以图片形式存在，需要 OCR，`source="extracted"` 并带置信度。评分会对低置信度的尺码表扣分。
5. `occasions` 可以由类目、风格、季节这些属性生成（`source="derived"`），laya 靠它来匹配需求。
6. 平台原始数据完整放进 `raw`。

## 人物 `Person`

用户上传的存放在 `data/persons/<id>/`，内置示例在 `samples/persons/<id>/`（只读）。目录里有 `front.jpg`、`side.jpg`、`back.jpg`（侧面、背面可选）和 `profile.json`。

| 字段 | 说明 |
|---|---|
| `views` | 视角 → 文件名 |
| `photo_checks` | 每张照片的检查结果：`passed`、`blocking[]`（拦截原因）、`warnings[]`（提示）、`metrics`（测量值） |
| `profile` | `BodyProfile`：性别、身高、体重（必填），胸 / 腰 / 臀围、肩宽、常穿尺码（选填），都是 `Val`（`user_input`） |
| `measured` | 照片测量值：肩宽、胯宽、腿长比例（`measured`，只用来校验，不替代用户填写的数据） |
| `trust` | `trusted` / `suspicious` / `untrusted` / `unverified` |
| `issues[]` | 可信度问题：`level`、`field`、`message` |
| `version`、`updated_at` | 资料版本，修改资料时递增 |

照片的预处理结果（姿态、解析、遮挡图）由换装服务缓存在内存里，用户上传一次后可以一直复用。
