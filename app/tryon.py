import os
import threading
import time

import cv2
import numpy as np
import torch
from PIL import Image

from fashn_human_parser import CATEGORY_TO_BODY_COVERAGE
from fashn_vton import TryOnPipeline
from fashn_vton.preprocessing import BODY_COVERAGE_TO_FASHN_LABELS, FASHN_LABELS_TO_IDS, create_garment_image
from fashn_vton.dwpose import draw_pose
from fashn_vton.utils import get_dummy_dw_keypoints, get_rf_schedule, normalize_uint8_to_neg1_1, numpy_to_torch, tensor_to_pil

import config

WEIGHTS = config.FASHN_WEIGHTS

CATEGORY = {"upper": "tops", "lower": "bottoms", "overall": "one-pieces"}

# FASHN VTON v1.5 is maskless: it sees the whole person while generating, so body shape, pose and face are kept.
# guidance 1.0 skips the unconditional pass entirely (half the compute); quality mode keeps CFG.
MODES = {
    "turbo": {"steps": 6, "guidance": 1.0, "preview_every": 1},
    "fast": {"steps": 10, "guidance": 1.0, "preview_every": 2},
    "quality": {"steps": 20, "guidance": 1.5, "preview_every": 4},
}


# FASHN human-parser labels
FACE, HAIR, TOP, DRESS, SKIRT, PANTS, BELT, SCARF, ARMS, HANDS, FEET = 1, 2, 3, 4, 5, 6, 7, 10, 12, 13, 15
OLD_CLOTHES = {"tops": [TOP, DRESS, SCARF], "bottoms": [SKIRT, PANTS, BELT], "one-pieces": [TOP, DRESS, SCARF, SKIRT, PANTS, BELT]}
MASK_VALUE = 127
# standing-height fractions (adult anthropometry): shoulder line ≈ 0.82, natural waist ≈ 0.62 of stature above the floor
SHOULDER_HEIGHT, WAIST_HEIGHT = 0.82, 0.62


def build_agnostic(entry, category, fit):
    """Grey out what the new garment may occupy. Returns the image and a summary of what was masked."""
    arr, seg = entry["arr"], entry["seg"]
    h, w = seg.shape[:2]
    rows = np.nonzero((seg != 0).any(axis=1))[0]
    top, bottom = int(rows.min()), int(rows.max())
    stature = bottom - top
    fit = fit or {}

    region = np.isin(seg, OLD_CLOTHES[category])
    if fit.get("mask_arms"):
        region |= seg == ARMS
    info = {"hem_y": None, "length_calibrated": False}
    if fit.get("length_cm") and fit.get("height_cm"):
        px_per_cm = stature / fit["height_cm"]
        start_y = bottom - (SHOULDER_HEIGHT if fit["start"] == "shoulder" else WAIST_HEIGHT) * stature
        hem_y = int(min(start_y + fit["length_cm"] * px_per_cm, bottom - 0.01 * stature))
        band = slice(int(start_y), hem_y)
        cols = np.nonzero((seg[band] != 0).any(axis=0))[0]
        if len(cols):
            margin = int(0.05 * stature)  # room for flared skirts / loose hems
            region[band, max(cols.min() - margin, 0):min(cols.max() + margin, w)] = True
        info.update(hem_y=hem_y / h, length_calibrated=True)
    region = cv2.dilate(region.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))).astype(bool)
    keep = [FACE, HAIR, FEET, HANDS] + ([] if fit.get("mask_arms") else [ARMS])  # arms beside the hips are not garment
    region &= ~np.isin(seg, keep)
    ca = arr.copy()
    ca[region] = MASK_VALUE
    info["masked_ratio"] = round(float(region.mean()), 3)
    return ca, info


LEGS = 14
NEW_GARMENT = {"tops": [TOP, DRESS], "bottoms": [SKIRT, PANTS], "one-pieces": [DRESS, TOP, SKIRT, PANTS]}


def quality_check(entry, seg_result, category, info, fit):
    """Measure the generated image against the plan: hem position vs the size chart, and whether the visible legs
    kept their width. Returns only what could actually be measured."""
    seg0 = entry["seg"]
    h, w = seg0.shape[:2]
    rows = np.nonzero((seg0 != 0).any(axis=1))[0]
    top, bottom = int(rows.min()), int(rows.max())
    stature = bottom - top
    qc = {}
    garment_rows = np.nonzero(np.isin(seg_result, NEW_GARMENT[category]).sum(axis=1) > 0.02 * w)[0]
    hem = int(garment_rows.max()) if len(garment_rows) else None
    if hem is not None and info.get("hem_y") is not None and fit and fit.get("height_cm"):
        px_per_cm = stature / fit["height_cm"]
        qc["length_diff_cm"] = round((hem - info["hem_y"] * h) / px_per_cm, 1)  # negative = shorter than the chart
    start = max(hem or 0, int(top + 0.55 * stature))
    end = int(bottom - 0.08 * stature)  # stop above the shoes
    if end - start > 10:
        w0 = (seg0[start:end] == LEGS).sum(axis=1)
        w1 = (seg_result[start:end] == LEGS).sum(axis=1)
        both = (w0 > 5) & (w1 > 5)
        if both.sum() > 10:
            qc["leg_width_ratio"] = round(float(np.median(w1[both] / w0[both])), 2)
    return qc


class TryOnEngine:
    def __init__(self):
        self.status = "idle"
        self.error = None
        self.pipe = None
        self._lock = threading.Lock()
        self._person_cache = {}
        self._cloth_cache = {}

    def load_async(self, on_ready=None):
        threading.Thread(target=self._load, args=(on_ready,), daemon=True).start()

    def _load(self, on_ready=None):
        try:
            self.status = "loading"
            self.pipe = TryOnPipeline(weights_dir=WEIGHTS)
            self.status = "ready"
            if on_ready:
                on_ready()
        except Exception as e:
            self.error = repr(e)
            self.status = "error"
            raise

    def _tensor(self, img):
        t = numpy_to_torch(img)
        while t.dim() < 4:  # grayscale pose maps come back as (H, W)
            t = t.unsqueeze(0)
        return normalize_uint8_to_neg1_1(t).to(self.pipe.device, dtype=self.pipe.inference_dtype)

    def _person(self, person_key, person_path, category, fit=None):
        """Pose + clothing-agnostic input for a person photo.

        Only the old clothes are masked, never the whole limb: FASHN's default limb masking lets the model redraw
        legs/arms from its own prior (legs came out ~30% thinner). Where the new garment should reach is taken from
        the size chart (fit["length_cm"]) and the user's height, and that band is masked too, so the garment gets
        its real length while everything below the hem stays the real person."""
        p = self.pipe
        if person_key not in self._person_cache:
            arr = np.array(p.pre_resize(Image.open(person_path).convert("RGB"), allow_upsampling=False))
            pose = p.pose_model(arr[..., ::-1])
            self._person_cache[person_key] = {
                "arr": arr,
                "seg": p.hp_model.predict(arr),
                "pose": self._tensor(p.resize_pad_fn(draw_pose(pose, arr.shape[0], arr.shape[1], grayscale=True),
                                                     interpolation=cv2.INTER_NEAREST_EXACT)),
                "ca": {},
            }
        entry = self._person_cache[person_key]
        key = (category, tuple(sorted((fit or {}).items())))
        if key not in entry["ca"]:
            ca, region = build_agnostic(entry, category, fit)
            entry["ca"][key] = (self._tensor(p.resize_pad_fn(ca, mem_padding=True)), region)
        ca, region = entry["ca"][key]
        return {"ca": ca, "pose": entry["pose"], "region": region}

    def _garment(self, cloth_path, category):
        key = (cloth_path, os.path.getmtime(cloth_path), category)
        if key not in self._cloth_cache:
            p = self.pipe
            arr = np.array(p.pre_resize(Image.open(cloth_path).convert("RGB"), allow_upsampling=False))
            coverage = CATEGORY_TO_BODY_COVERAGE.get(category)
            labels = [FASHN_LABELS_TO_IDS[x] for x in BODY_COVERAGE_TO_FASHN_LABELS.get(coverage)]
            garment = create_garment_image(img_np=arr, seg_pred=p.hp_model.predict(arr), labels_to_segment_indices=labels,
                                           disable_masking=True)
            pose = draw_pose(get_dummy_dw_keypoints(), arr.shape[0], arr.shape[1], grayscale=True)
            self._cloth_cache[key] = {
                "image": self._tensor(p.resize_pad_fn(garment)),
                "pose": self._tensor(p.resize_pad_fn(pose, interpolation=cv2.INTER_NEAREST_EXACT)),
            }
        return self._cloth_cache[key]

    def analyze_photo(self, path):
        """Raw pose + parsing of a user photo, for upload checks."""
        if self.status != "ready":
            raise RuntimeError(f"试衣模型尚未就绪（{self.status}）")
        with self._lock:
            p = self.pipe
            img = Image.open(path).convert("RGB")
            arr = np.array(p.pre_resize(img, allow_upsampling=False))
            kp, score = p.pose_model.pose_estimation(arr[..., ::-1])
            return {"orig_size": img.size, "arr": arr, "kp": kp, "score": score, "seg": p.hp_model.predict(arr)}

    def prepare(self, person_key, person_path, mask_types, cloth_paths=()):
        if self.status != "ready":
            return
        with self._lock:
            for mt in mask_types:
                if person_key:
                    self._person(person_key, person_path, CATEGORY[mt])
                for cp in cloth_paths:
                    self._garment(cp, CATEGORY[mt])

    def _to_pil(self, x):
        return self.pipe.resize_pad_fn.unpad(tensor_to_pil(x[0].float().clamp(-1, 1), unnormalize=True))

    @torch.inference_mode()
    def _sample(self, person, garment, category, cfg, seed, on_preview):
        p, model = self.pipe, self.pipe.tryon_model
        generator = torch.Generator(device=p.device).manual_seed(seed)
        c, h, w = model.channels_in, *model.input_shape
        x = torch.randn((1, c, h, w), generator=generator, device=p.device, dtype=p.inference_dtype)
        kwargs = {
            "ca_images": person["ca"], "person_poses": person["pose"],
            "garment_images": garment["image"], "garment_poses": garment["pose"],
            "garment_categories": torch.tensor([p.CATEGORY_TO_LABEL[category]], device=p.device),
        }
        timesteps = get_rf_schedule(num_steps=cfg["steps"], mu=1.5)
        n = len(timesteps) - 1
        for i, (t_curr, t_next) in enumerate(zip(timesteps[:-1], timesteps[1:])):
            t_vec = torch.full((1,), t_curr, dtype=x.dtype, device=x.device)
            if cfg["guidance"] > 1.0 and i < n - 1:
                pred = model.forward_for_cfg(x, t_vec, **kwargs)
                v = pred["v_u"] + cfg["guidance"] * (pred["v_c"] - pred["v_u"])
            else:
                v = model.forward(x, t_vec, **kwargs)["x"]
            if on_preview and i < n - 1 and i % cfg["preview_every"] == 0:
                # rectified flow runs noise (t=0) -> image (t=1), so the current image estimate is x + (1 - t) * v
                on_preview(self._to_pil(x + (1 - t_curr) * v), i + 1, n)
            x = x + (t_next - t_curr) * v
        return self._to_pil(x)

    def run(self, person_key, person_path, cloth_path, mask_type, mode="fast", seed=42, on_preview=None, fit=None):
        if self.status != "ready":
            raise RuntimeError(f"试衣模型尚未就绪（{self.status}）")
        cfg = MODES[mode]
        category = CATEGORY[mask_type]
        with self._lock:
            t0 = time.perf_counter()
            person = self._person(person_key, person_path, category, fit)
            garment = self._garment(cloth_path, category)
            t_prep = time.perf_counter() - t0
            result = self._sample(person, garment, category, cfg, seed, on_preview)
            entry = self._person_cache[person_key]
            h, w = entry["seg"].shape[:2]
            seg_result = self.pipe.hp_model.predict(np.array(result.resize((w, h), Image.BILINEAR)))
            qc = quality_check(entry, seg_result, category, person["region"], fit)
            return result, {
                "prep_ms": round(t_prep * 1000),
                "total_ms": round((time.perf_counter() - t0) * 1000),
                "steps": cfg["steps"],
                "mask": person["region"],
                "qc": qc,
            }
