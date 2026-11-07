"""Subject size, sharpness, and people-scene filters for bird photos.

Species ID is not enough: a correctly identified bird can still be a speck,
out of focus, or a crowd scene. These metrics run after (or without) ID.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image, ImageFilter

COCO_PERSON = 1
COCO_BIRD = 16

_DETECTOR = None
_DETECTOR_TFM = None
_DETECTOR_DEVICE = ""


@dataclass
class QualityThresholds:
    """二次审查默认偏保守：只过滤主体特别小（≤ 2.5%）的图。"""

    min_bird_frac: float = 0.025
    min_detect_score: float = 0.25
    drop_if_no_bird: bool = True
    min_crop_lap: float = 70.0
    max_crop_fft: float = 8.0
    people_min_count: int = 3
    people_outweigh_bird: bool = True


@dataclass
class QualityMetrics:
    width: int = 0
    height: int = 0
    min_side: int = 0
    bytes: int = 0
    bird_n: int = 0
    bird_max: float = 0.0
    bird_sum: float = 0.0
    bird_score: float = 0.0
    person_n: int = 0
    person_max: float = 0.0
    crop_lap: Optional[float] = None
    crop_crete: Optional[float] = None
    crop_fft: Optional[float] = None
    full_lap: float = 0.0
    detect_ok: bool = False
    detect_error: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["extra"] = dict(self.extra)
        return payload


def detector_available() -> bool:
    try:
        import torch  # noqa: F401
        import torchvision  # noqa: F401
    except ImportError:
        return False
    return True


def _device() -> str:
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _load_detector():
    global _DETECTOR, _DETECTOR_TFM, _DETECTOR_DEVICE
    if _DETECTOR is not None:
        return _DETECTOR, _DETECTOR_TFM
    import torch
    from torchvision.models.detection import (
        FasterRCNN_MobileNet_V3_Large_FPN_Weights,
        fasterrcnn_mobilenet_v3_large_fpn,
    )

    weights = FasterRCNN_MobileNet_V3_Large_FPN_Weights.DEFAULT
    device = _device()
    print(f"Loading Faster R-CNN MobileNet bird detector ({device})…", flush=True)
    model = fasterrcnn_mobilenet_v3_large_fpn(weights=weights)
    model.eval()
    model.to(device)
    _DETECTOR = model
    _DETECTOR_TFM = weights.transforms()
    _DETECTOR_DEVICE = device
    return _DETECTOR, _DETECTOR_TFM


def cache_path(cache_dir: Path, sha1: str) -> Path:
    return cache_dir / "detect_frcnn" / f"{sha1}.json"


def load_cached_detect(cache_dir: Path, sha1: str) -> Optional[dict]:
    path = cache_path(cache_dir, sha1)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_cached_detect(cache_dir: Path, sha1: str, payload: dict) -> None:
    path = cache_path(cache_dir, sha1)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def laplacian_variance(gray: np.ndarray) -> float:
    padded = np.pad(gray.astype(np.float32), 1, mode="edge")
    lap = (
        padded[:-2, 1:-1]
        + padded[2:, 1:-1]
        + padded[1:-1, :-2]
        + padded[1:-1, 2:]
        - 4 * padded[1:-1, 1:-1]
    )
    return float(lap.var())


def crete_blur(gray_img: Image.Image) -> float:
    """Crete 2007 感知模糊：0 更锐、1 更糊。"""
    gray = np.asarray(gray_img, dtype=np.float32)
    blurred = np.asarray(gray_img.filter(ImageFilter.BoxBlur(3)), dtype=np.float32)
    dh = np.abs(np.diff(gray, axis=1))
    dbh = np.abs(np.diff(blurred, axis=1))
    dv = np.abs(np.diff(gray, axis=0))
    dbv = np.abs(np.diff(blurred, axis=0))
    vh = np.maximum(0, dh - dbh)
    vv = np.maximum(0, dv - dbv)
    blur_h = float((dh.sum() - vh.sum()) / (dh.sum() or 1.0))
    blur_v = float((dv.sum() - vv.sum()) / (dv.sum() or 1.0))
    return max(blur_h, blur_v)


def fft_mid_high_ratio(gray: np.ndarray) -> float:
    """频谱中频/高频比。特别糊、只剩色块噪声的图会偏高。"""
    arr = gray.astype(np.float32)
    arr = arr - float(arr.mean())
    spectrum = np.abs(np.fft.fftshift(np.fft.fft2(arr)))
    height, width = spectrum.shape
    center_y, center_x = height // 2, width // 2
    yy, xx = np.ogrid[:height, :width]
    radius = np.sqrt((yy - center_y) ** 2 + (xx - center_x) ** 2)
    rmax = float(radius.max() or 1.0)
    mid = float(spectrum[(radius >= 0.1 * rmax) & (radius < 0.35 * rmax)].mean())
    high = float(spectrum[radius >= 0.35 * rmax].mean())
    return mid / (high + 1e-6)


def _resize_gray(img: Image.Image, max_side: int) -> Image.Image:
    gray = img.convert("L")
    width, height = gray.size
    scale = max_side / max(width, height)
    if scale < 1:
        gray = gray.resize(
            (max(1, int(width * scale)), max(1, int(height * scale))),
            Image.BILINEAR,
        )
    return gray


def _detect_boxes(image: Image.Image) -> list[dict]:
    import torch

    model, transform = _load_detector()
    tensor = transform(image).to(_DETECTOR_DEVICE)
    with torch.no_grad():
        output = model([tensor])[0]
    labels = output["labels"].detach().cpu().tolist()
    scores = output["scores"].detach().cpu().tolist()
    boxes = output["boxes"].detach().cpu().tolist()
    rows: list[dict] = []
    width, height = image.size
    for label, score, box in zip(labels, scores, boxes):
        x1, y1, x2, y2 = box
        rows.append(
            {
                "label": int(label),
                "score": float(score),
                "xyxy_norm": [
                    float(x1) / width,
                    float(y1) / height,
                    float(x2) / width,
                    float(y2) / height,
                ],
            }
        )
    return rows


def _area_frac(xyxy_norm: list[float]) -> float:
    x1, y1, x2, y2 = xyxy_norm
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _crop_from_norm(image: Image.Image, xyxy_norm: list[float], pad: float = 0.15) -> Image.Image:
    width, height = image.size
    x1, y1, x2, y2 = xyxy_norm
    box_w = max(x2 - x1, 1e-6)
    box_h = max(y2 - y1, 1e-6)
    left = max(0, int((x1 - box_w * pad) * width))
    top = max(0, int((y1 - box_h * pad) * height))
    right = min(width, int((x2 + box_w * pad) * width))
    bottom = min(height, int((y2 + box_h * pad) * height))
    if right <= left:
        right = min(width, left + 1)
    if bottom <= top:
        bottom = min(height, top + 1)
    return image.crop((left, top, right, bottom))


def measure_image(
    path: Path,
    *,
    sha1: str = "",
    cache_dir: Optional[Path] = None,
    min_detect_score: float = 0.25,
) -> QualityMetrics:
    image = Image.open(path).convert("RGB")
    width, height = image.size
    metrics = QualityMetrics(
        width=width,
        height=height,
        min_side=min(width, height),
        bytes=path.stat().st_size,
        full_lap=laplacian_variance(np.asarray(_resize_gray(image, 384), dtype=np.float32)),
    )
    boxes: list[dict] = []
    if sha1 and cache_dir is not None:
        cached = load_cached_detect(cache_dir, sha1)
        if cached and cached.get("ok"):
            boxes = list(cached.get("boxes") or [])
            metrics.detect_ok = True
    if not metrics.detect_ok:
        if not detector_available():
            metrics.detect_error = "torch/torchvision not installed"
            return metrics
        try:
            boxes = _detect_boxes(image)
            metrics.detect_ok = True
            if sha1 and cache_dir is not None:
                save_cached_detect(
                    cache_dir,
                    sha1,
                    {"ok": True, "width": width, "height": height, "boxes": boxes},
                )
        except Exception as exc:  # noqa: BLE001
            metrics.detect_error = str(exc)
            return metrics

    birds: list[tuple[float, float, list[float]]] = []
    people: list[float] = []
    for row in boxes:
        score = float(row.get("score") or 0)
        if score < min_detect_score:
            continue
        area = _area_frac(list(row.get("xyxy_norm") or [0, 0, 0, 0]))
        label = int(row.get("label") or 0)
        if label == COCO_BIRD:
            birds.append((area, score, list(row.get("xyxy_norm") or [0, 0, 0, 0])))
        elif label == COCO_PERSON:
            people.append(area)
    birds.sort(key=lambda item: item[0], reverse=True)
    people.sort(reverse=True)
    metrics.bird_n = len(birds)
    if birds:
        metrics.bird_max = birds[0][0]
        metrics.bird_score = birds[0][1]
        metrics.bird_sum = float(sum(item[0] for item in birds[:8]))
        crop = _crop_from_norm(image, birds[0][2])
        crop_gray = _resize_gray(crop, 256)
        crop_arr = np.asarray(crop_gray, dtype=np.float32)
        metrics.crop_lap = laplacian_variance(crop_arr)
        metrics.crop_crete = crete_blur(crop_gray)
        metrics.crop_fft = fft_mid_high_ratio(crop_arr)
    metrics.person_n = len(people)
    metrics.person_max = people[0] if people else 0.0
    return metrics


def quality_fail_reasons(
    metrics: QualityMetrics,
    thresholds: QualityThresholds | None = None,
) -> list[str]:
    """返回要隔离的原因代码；空列表表示通过画质关。"""
    thresholds = thresholds or QualityThresholds()
    if not metrics.detect_ok:
        return []
    reasons: list[str] = []
    if metrics.bird_n == 0:
        if thresholds.drop_if_no_bird:
            reasons.append("quality_no_bird_box")
        return reasons
    if metrics.bird_max <= thresholds.min_bird_frac:
        reasons.append("quality_small_bird")
    if (
        thresholds.min_crop_lap > 0
        and metrics.crop_lap is not None
        and metrics.crop_lap < thresholds.min_crop_lap
    ):
        reasons.append("quality_blur_subject")
    if (
        thresholds.max_crop_fft > 0
        and metrics.crop_fft is not None
        and metrics.crop_fft >= thresholds.max_crop_fft
    ):
        reasons.append("quality_blur_spectrum")
    if (
        thresholds.people_outweigh_bird
        and metrics.person_n >= thresholds.people_min_count
        and metrics.person_max > metrics.bird_max
    ):
        reasons.append("quality_people_scene")
    return reasons
