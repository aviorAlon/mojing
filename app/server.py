import asyncio
import base64
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Literal

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps
from pydantic import BaseModel

import config
import fitting
import providers
import scoring
import validation
from models import CATEGORY_LABEL, TRYON_CATEGORY, BodyProfile, GarmentImage, Listing, Person, Val, now
from tryon import TryOnEngine

CATALOG_DIR = config.CATALOG_DIR
SAMPLES_DIR = config.SAMPLES_DIR
PERSONS_DIR = os.path.join(config.DATA_DIR, "persons")
RESULTS_DIR = os.path.join(config.DATA_DIR, "results")
VIDEOS_DIR = os.path.join(config.DATA_DIR, "videos")
LAYA_URL = config.LAYA_URL
VIEWS = ("front", "side", "back")
PERSON_ID = re.compile(r"[a-z0-9_]{3,40}")

PREVIEW_ENCODER = ThreadPoolExecutor(max_workers=1)

for d in (CATALOG_DIR, SAMPLES_DIR, PERSONS_DIR, RESULTS_DIR, VIDEOS_DIR):
    os.makedirs(d, exist_ok=True)

engine = TryOnEngine()


@asynccontextmanager
async def lifespan(_app):
    if config.ENGINE_ENABLED:
        engine.load_async(on_ready=_prewarm)
    else:
        engine.status = "disabled"
    yield


app = FastAPI(title="Laya TryOn", description="说一句话挑衣服，多视角真人换装", lifespan=lifespan)


async def read_image(upload: UploadFile) -> Image.Image:
    data = await upload.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(413, "图片不能超过 20MB")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        raise HTTPException(400, "无法识别的图片格式")
    return ImageOps.exif_transpose(img).convert("RGB")


def has_file(upload: UploadFile | None) -> bool:
    return upload is not None and bool(upload.filename)


# ---------- catalog (garments) ----------

def load_catalog() -> list[Listing]:
    listings = []
    for name in sorted(os.listdir(CATALOG_DIR)):
        path = os.path.join(CATALOG_DIR, name, "listing.json")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                listings.append(Listing.model_validate_json(f.read()))
    order = {"mock": 0, "manual": 1, "demo": 2}
    return sorted(listings, key=lambda x: order.get(x.platform, 3))


def find_listing(item_id) -> Listing:
    if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", item_id):
        raise HTTPException(400, "非法的商品 id")
    path = os.path.join(CATALOG_DIR, item_id, "listing.json")
    if not os.path.isfile(path):
        raise HTTPException(404, f"没有这个商品：{item_id}")
    with open(path, encoding="utf-8") as f:
        return Listing.model_validate_json(f.read())


def listing_json(x: Listing):
    front, back = x.image("front"), x.image("back")
    return {
        **x.model_dump(exclude={"raw"}),
        "category_label": CATEGORY_LABEL[x.category],
        "url": f"/catalog/{x.id}/{front.file}" if front else None,
        "url_back": f"/catalog/{x.id}/{back.file}" if back else None,
        "capabilities": x.capabilities(),
    }


def garment_file(x: Listing, view):
    img = x.image("back" if view == "back" else "front")
    return os.path.join(CATALOG_DIR, x.id, img.file) if img else None


def _categories():
    return sorted({x.tryon_category for x in load_catalog()})


@app.get("/api/wardrobe")
def wardrobe():
    return [listing_json(x) for x in load_catalog()]


@app.post("/api/wardrobe")
async def add_item(
    image: UploadFile = File(...),
    image_back: UploadFile | None = File(None),
    name: str = Form(...),
    occasions: str = Form(""),
    category: str = Form("top"),
):
    if category not in TRYON_CATEGORY:
        raise HTTPException(400, f"category 只能是 {list(TRYON_CATEGORY)}")
    item_id = "manual_" + uuid.uuid4().hex[:8]
    folder = os.path.join(CATALOG_DIR, item_id)
    os.makedirs(folder)
    (await read_image(image)).save(os.path.join(folder, "front.jpg"), quality=95)
    images = [GarmentImage(file="front.jpg", kind="flat_lay", view="front", source="user_input")]
    if has_file(image_back):
        (await read_image(image_back)).save(os.path.join(folder, "back.jpg"), quality=95)
        images.append(GarmentImage(file="back.jpg", kind="flat_lay", view="back", source="user_input"))
    listing = Listing(id=item_id, platform="manual", item_id=item_id, title=name.strip()[:60] or "未命名单品",
                      category=category, category_path=["手动添加"], images=images,
                      occasions=Val(value=occasions.strip()[:60], source="user_input") if occasions.strip() else Val())
    with open(os.path.join(folder, "listing.json"), "w", encoding="utf-8") as f:
        f.write(listing.model_dump_json(indent=2))
    return {"id": item_id}


@app.delete("/api/wardrobe/{item_id}")
def delete_item(item_id: str):
    find_listing(item_id)
    shutil.rmtree(os.path.join(CATALOG_DIR, item_id))
    return {"ok": True}


# ---------- persons ----------

def person_dir(person_id) -> tuple[str, bool]:
    """Folder of a person and whether it is a bundled (read-only) sample."""
    if not PERSON_ID.fullmatch(person_id):
        raise HTTPException(400, "非法的模特 id")
    for base, sample in ((PERSONS_DIR, False), (SAMPLES_DIR, True)):
        folder = os.path.join(base, person_id)
        if os.path.isfile(os.path.join(folder, "front.jpg")):
            return folder, sample
    raise HTTPException(404, "找不到这个模特，请重新上传")


def load_person(person_id) -> Person | None:
    path = os.path.join(person_dir(person_id)[0], "profile.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return Person.model_validate_json(f.read())


def save_person(person: Person):
    with open(os.path.join(PERSONS_DIR, person.id, "profile.json"), "w", encoding="utf-8") as f:
        f.write(person.model_dump_json(indent=2))


def person_views(person_id):
    """Returns {view: absolute path}."""
    folder, _ = person_dir(person_id)
    return {v: os.path.join(folder, v + ".jpg") for v in VIEWS if os.path.isfile(os.path.join(folder, v + ".jpg"))}


def person_json(person_id):
    folder, sample = person_dir(person_id)
    views = person_views(person_id)
    person = load_person(person_id)
    mtime = int(os.path.getmtime(views["front"]))
    mount = "samples" if sample else "persons"
    data = {"id": person_id, "sample": sample, "views": {v: f"/{mount}/{person_id}/{v}.jpg?v={mtime}" for v in views}}
    if sample:
        data["note"] = "内置示例模特（只读）"
    if person is None:
        return {**data, "trust": "unverified", "issues": [], "warnings": [], "profile": None, "note": "没有身材数据"}
    grouped = {}
    for v, c in person.photo_checks.items():
        for w in c.warnings:
            grouped.setdefault(w, []).append(validation.VIEW_LABEL[v])
    warnings = [f"{'/'.join(labels)}：{w}" for w, labels in grouped.items()]
    return {"note": None, **data, "trust": person.trust, "issues": [i.model_dump() for i in person.issues], "warnings": warnings,
            "profile": person.profile.model_dump(), "measured": {k: v.model_dump() for k, v in person.measured.items()},
            "updated_at": person.updated_at, "version": person.version}


def _engine_key(person_id, view):
    return f"{person_id}#{view}"


def _prepare_in_background(person_id):
    views = person_views(person_id)

    def work():
        for view, path in views.items():
            engine.prepare(_engine_key(person_id, view), path, _categories())

    threading.Thread(target=work, daemon=True).start()


def _prewarm():
    for x in load_catalog():
        paths = [p for p in (garment_file(x, "front"), garment_file(x, "back")) if p]
        engine.prepare(None, None, [x.tryon_category], paths)
    for pid in [p["id"] for p in persons()]:
        for view, path in person_views(pid).items():
            engine.prepare(_engine_key(pid, view), path, _categories())


@app.get("/api/persons")
def persons():
    def listed(base):
        ids = [p for p in os.listdir(base) if PERSON_ID.fullmatch(p) and os.path.isfile(os.path.join(base, p, "front.jpg"))]
        return sorted(ids, key=lambda p: os.path.getmtime(os.path.join(base, p, "front.jpg")), reverse=True)

    return [person_json(pid) for pid in listed(PERSONS_DIR) + sorted(listed(SAMPLES_DIR))]


def _num(x: str | None):
    if x is None or not str(x).strip():
        return None
    try:
        return float(x)
    except ValueError:
        raise HTTPException(400, f"不是有效的数字：{x}")


def build_profile(gender, height_cm, weight_kg, chest_cm, waist_cm, hip_cm, shoulder_cm, usual_top_size, usual_bottom_size):
    def val(v):
        return Val(value=v, source="user_input") if v not in (None, "") else Val()

    if gender not in ("female", "male"):
        raise HTTPException(400, "请选择性别")
    profile = BodyProfile(
        gender=val(gender), height_cm=val(_num(height_cm)), weight_kg=val(_num(weight_kg)),
        chest_cm=val(_num(chest_cm)), waist_cm=val(_num(waist_cm)), hip_cm=val(_num(hip_cm)), shoulder_cm=val(_num(shoulder_cm)),
        usual_top_size=val((usual_top_size or "").strip()[:8]), usual_bottom_size=val((usual_bottom_size or "").strip()[:8]),
    )
    if not profile.height_cm.known or not profile.weight_kg.known:
        raise HTTPException(400, "身高和体重是必填项")
    return profile


@app.post("/api/person")
async def create_person(
    front: UploadFile = File(...),
    side: UploadFile | None = File(None),
    back: UploadFile | None = File(None),
    gender: str = Form(...),
    height_cm: str = Form(...),
    weight_kg: str = Form(...),
    chest_cm: str | None = Form(None),
    waist_cm: str | None = Form(None),
    hip_cm: str | None = Form(None),
    shoulder_cm: str | None = Form(None),
    usual_top_size: str | None = Form(None),
    usual_bottom_size: str | None = Form(None),
):
    if engine.status != "ready":
        raise HTTPException(503, "模型还在加载，稍后再试（照片检查需要用到它）")
    profile = build_profile(gender, height_cm, weight_kg, chest_cm, waist_cm, hip_cm, shoulder_cm, usual_top_size, usual_bottom_size)

    staging = tempfile.mkdtemp(dir=PERSONS_DIR, prefix=".upload_")
    try:
        checks = {}
        for view, upload in (("front", front), ("side", side), ("back", back)):
            if not has_file(upload):
                continue
            img = await read_image(upload)
            path = os.path.join(staging, view + ".jpg")
            img.thumbnail((1536, 1536))
            img.save(path, quality=95)
            analysis = await run_in_threadpool(engine.analyze_photo, path)
            checks[view] = validation.check_photo(analysis, view)
        if any(not c.passed for c in checks.values()):
            return JSONResponse(status_code=422, content={
                "detail": "有照片没通过检查，请按提示重拍",
                "checks": {v: c.model_dump(exclude={"metrics"}) for v, c in checks.items()},
            })
        person_id = uuid.uuid4().hex[:12]
        folder = os.path.join(PERSONS_DIR, person_id)
        os.rename(staging, folder)
        staging = None
    finally:
        if staging:
            shutil.rmtree(staging, ignore_errors=True)

    person = Person(id=person_id, views={v: v + ".jpg" for v in checks}, photo_checks=checks, profile=profile)
    save_person(validation.assess(person))
    _prepare_in_background(person_id)
    return person_json(person_id)


@app.put("/api/person/{person_id}/profile")
async def update_profile(
    person_id: str,
    gender: str = Form(...),
    height_cm: str = Form(...),
    weight_kg: str = Form(...),
    chest_cm: str | None = Form(None),
    waist_cm: str | None = Form(None),
    hip_cm: str | None = Form(None),
    shoulder_cm: str | None = Form(None),
    usual_top_size: str | None = Form(None),
    usual_bottom_size: str | None = Form(None),
):
    if person_dir(person_id)[1]:
        raise HTTPException(403, "内置示例模特不能修改")
    person = load_person(person_id)
    if person is None:
        raise HTTPException(404, "这个模特没有资料可更新，请重新创建")
    person.profile = build_profile(gender, height_cm, weight_kg, chest_cm, waist_cm, hip_cm, shoulder_cm, usual_top_size, usual_bottom_size)
    person.version += 1
    person.updated_at = now()
    save_person(validation.assess(person))
    return person_json(person_id)


@app.delete("/api/person/{person_id}")
def delete_person(person_id: str):
    folder, sample = person_dir(person_id)
    if sample:
        raise HTTPException(403, "内置示例模特不能删除")
    shutil.rmtree(folder)
    return {"ok": True}


class PrepareReq(BaseModel):
    person_id: str


@app.post("/api/prepare")
def prepare(req: PrepareReq):
    if engine.status == "ready":
        _prepare_in_background(req.person_id)
    return {"ok": True}


# ---------- laya ----------

@app.get("/api/status")
async def status():
    laya_ok = False
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            r = await client.get(LAYA_URL.rsplit("/v1/", 1)[0] + "/health")
            laya_ok = r.status_code == 200
    except httpx.HTTPError:
        pass
    return {"tryon": engine.status, "tryon_error": engine.error, "laya": laya_ok}


class ChooseReq(BaseModel):
    text: str
    current_item: str | None = None


def occasion_key(x: Listing):
    return x.occasions.value if x.occasions.known else x.title


@app.post("/api/choose")
async def choose(req: ChooseReq):
    # laya matches mainly on the option key text, so the key is the occasion phrase (8/8 vs 3/8 with ids in A/B tests)
    catalog = load_catalog()
    items = [x for x in catalog if x.id != req.current_item] or catalog
    if not items:
        raise HTTPException(400, "衣柜是空的")
    key_to_item = {}
    for x in items:
        key = occasion_key(x)
        while key in key_to_item:
            key += "·"
        key_to_item[key] = x
    payload = {
        "state": {"text": req.text.strip()},
        "questions": {
            "outfit": {
                "type": "choice",
                "instructions": "用户要去什么场合？",
                "criteria": {k: x.title for k, x in key_to_item.items()},
            }
        },
    }
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(LAYA_URL, json=payload)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as e:
        raise HTTPException(503, f"laya 服务不可用：{e}")
    latency = round((time.perf_counter() - t0) * 1000)
    answer = data.get("answers", {}).get("outfit", {})
    if answer.get("choice") not in key_to_item:
        raise HTTPException(502, f"laya 返回了未知选项：{answer}")
    probs = {key_to_item[k].id: p for k, p in (answer.get("probabilities") or {}).items() if k in key_to_item}
    return {
        "choice": key_to_item[answer["choice"]].id,
        "matched_occasion": answer["choice"],
        "probabilities": probs,
        "confidence": answer.get("confidence"),
        "model": (data.get("routing") or {}).get("model"),
        "latency_ms": latency,
    }


# ---------- reliability score ----------

@app.get("/api/score")
def score(person_id: str, item_id: str, mode: Literal["turbo", "fast", "quality"] = "fast"):
    listing = find_listing(item_id)
    views = person_views(person_id)
    person = load_person(person_id)
    caps = listing.capabilities()
    plan = fitting.fit_plan(listing, person)["summary"]
    return {
        view: scoring.score_tryon(person, listing, view, mode, plan)
        for view in views
        if not (view == "back" and not caps["tryon_back"]["ok"])
    }


# ---------- try-on ----------

class TryOnReq(BaseModel):
    person_id: str
    item_id: str
    view: Literal["front", "side", "back"] = "front"
    mode: Literal["turbo", "fast", "quality"] = "fast"
    seed: int = 42


def _resolve(req: TryOnReq):
    listing = find_listing(req.item_id)
    views = person_views(req.person_id)
    if req.view not in views:
        raise HTTPException(400, f"这个模特没有{validation.VIEW_LABEL[req.view]}照片")
    cloth = garment_file(listing, req.view)
    if cloth is None:
        cap = listing.capabilities()["tryon_back" if req.view == "back" else "tryon_front"]
        raise HTTPException(409, cap["reason"])
    plan = fitting.fit_plan(listing, load_person(req.person_id))
    return listing, views[req.view], cloth, plan


def to_data_url(img, quality):
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def save_result(result, timing, req: "TryOnReq", listing: Listing, plan):
    name = f"{int(time.time())}_{uuid.uuid4().hex[:6]}.jpg"
    buf = io.BytesIO()
    result.save(buf, format="JPEG", quality=92)
    with open(os.path.join(RESULTS_DIR, name), "wb") as f:
        f.write(buf.getvalue())
    score = scoring.score_tryon(load_person(req.person_id), listing, req.view, req.mode, plan["summary"], timing["qc"])
    return {"image": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(), "url": f"/results/{name}",
            "timing": {k: v for k, v in timing.items() if k not in ("mask", "qc")}, "view": req.view,
            "fit": {**plan["summary"], "hem_y": timing["mask"]["hem_y"]}, "qc": timing["qc"], "score": score}


@app.post("/api/tryon")
async def tryon(req: TryOnReq):
    listing, p_path, cloth, plan = _resolve(req)
    try:
        result, timing = await run_in_threadpool(
            engine.run, _engine_key(req.person_id, req.view), p_path, cloth, listing.tryon_category, req.mode, req.seed,
            None, plan["engine"],
        )
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return save_result(result, timing, req, listing, plan)


@app.post("/api/tryon/stream")
async def tryon_stream(req: TryOnReq):
    listing, p_path, cloth, plan = _resolve(req)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    t0 = time.perf_counter()

    def emit(msg):
        loop.call_soon_threadsafe(queue.put_nowait, msg)

    def on_preview(img, step, total):
        elapsed = round((time.perf_counter() - t0) * 1000)
        PREVIEW_ENCODER.submit(lambda: emit({"type": "preview", "step": step, "total": total, "view": req.view,
                                             "image": to_data_url(img, 70), "elapsed_ms": elapsed}))

    def work():
        try:
            result, timing = engine.run(
                _engine_key(req.person_id, req.view), p_path, cloth, listing.tryon_category, req.mode, req.seed, on_preview,
                plan["engine"],
            )
            done = {"type": "done", **save_result(result, timing, req, listing, plan)}
        except Exception as e:
            done = {"type": "error", "detail": str(e)}
        PREVIEW_ENCODER.submit(emit, done)  # single worker keeps it ordered after the last preview

    loop.run_in_executor(None, work)

    async def lines():
        while True:
            msg = await queue.get()
            yield json.dumps(msg, ensure_ascii=False) + "\n"
            if msg["type"] in ("done", "error"):
                return

    return StreamingResponse(lines(), media_type="application/x-ndjson")


# ---------- turnaround video (user-configured provider, see docs/generation.md) ----------

_video = {}


def video_backend():
    if "provider" not in _video:
        _video["provider"] = providers.video_provider()  # raises ProviderNotConfigured
    return _video["provider"]


def result_file(url):
    name = os.path.basename(url.split("?")[0])
    path = os.path.join(RESULTS_DIR, name)
    if not url.startswith("/results/") or not os.path.isfile(path):
        raise HTTPException(400, "换装结果不存在，请先完成换装")
    return path


def _video_path(job_id):
    return os.path.join(VIDEOS_DIR, hashlib.sha1(job_id.encode()).hexdigest()[:20] + ".mp4")


class VideoReq(BaseModel):
    front_url: str
    back_url: str | None = None


@app.get("/api/video/config")
def video_config():
    return {**providers.video_status(), "seconds": config.VIDEO_SECONDS}


@app.post("/api/video")
async def create_video(req: VideoReq):
    try:
        backend = video_backend()
    except providers.ProviderNotConfigured as e:
        raise HTTPException(501, str(e))
    with open(result_file(req.front_url), "rb") as f:
        first = f.read()
    last = None
    if req.back_url:
        with open(result_file(req.back_url), "rb") as f:
            last = f.read()
    prompt = ("同一位人物站在原地，缓慢平稳地转身，从正面转到背面，完整展示身上这套衣服的正面、侧面和背面。"
              "镜头固定不动，背景和光线保持不变，服装的颜色、图案和版型始终保持一致，动作自然。") if last else (
             "人物站在原地缓慢平稳地转身一整圈，依次展示身上这套衣服的正面、侧面和背面，最后转回正面。"
             "镜头固定不动，背景和光线保持不变，服装的颜色、图案和版型始终保持一致，动作自然。")
    try:
        job_id = await run_in_threadpool(backend.submit, prompt, first, last, config.VIDEO_SECONDS)
    except Exception as e:
        raise HTTPException(502, f"视频生成接口出错：{e}")
    return {"request_id": str(job_id)}


@app.get("/api/video/{job_id}")
async def video_status(job_id: str):
    if not 1 <= len(job_id) <= 200:
        raise HTTPException(400, "非法的任务 id")
    local = _video_path(job_id)
    if os.path.isfile(local):
        return {"status": "done", "url": f"/videos/{os.path.basename(local)}"}
    try:
        state = await run_in_threadpool(video_backend().poll, job_id)
    except providers.ProviderNotConfigured as e:
        raise HTTPException(501, str(e))
    except Exception as e:
        raise HTTPException(502, f"视频生成接口出错：{e}")
    if state.get("status") == "done" and state.get("video"):
        with open(local, "wb") as f:
            f.write(state["video"])
        return {"status": "done", "url": f"/videos/{os.path.basename(local)}"}
    return {"status": state.get("status", "pending"), "error": state.get("error")}


app.mount("/catalog", StaticFiles(directory=CATALOG_DIR), name="catalog")
app.mount("/videos", StaticFiles(directory=VIDEOS_DIR), name="videos")
app.mount("/samples", StaticFiles(directory=SAMPLES_DIR), name="samples")
app.mount("/persons", StaticFiles(directory=PERSONS_DIR), name="persons")
app.mount("/results", StaticFiles(directory=RESULTS_DIR), name="results")
app.mount("/static", StaticFiles(directory=config.WEB_DIR), name="static")


@app.get("/")
def index():
    # stamp asset URLs with their modification time so browsers never run a stale app.js after an update
    version = max(int(os.path.getmtime(os.path.join(config.WEB_DIR, f))) for f in ("app.js", "style.css"))
    with open(os.path.join(config.WEB_DIR, "index.html"), encoding="utf-8") as f:
        html = f.read().replace("__V__", str(version))
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})
