"""Museum specimen / study-skin filters.

Two independent gates:

1. Source URL or credit is a known museum image host.
2. Frame has a color-calibration card AND a near-gray/white/black studio
   background. Colorful live birds on green bokeh must not trip this.

Does not try to detect dead or sick birds in the field.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

# Full host suffixes so "naturalis.nl" does not match "inaturalist.org".
MUSEUM_HOST_SUFFIXES = (
    "unimus.no",
    "naturalis.nl",
    "aucklandmuseum.com",
    "australian.museum",
    "collections.nmnh.si.edu",
    "nmnh.si.edu",
    "archimg.mnhn.lu",
    "mnhn.fr",
    "specify-media.science.ku.dk",
    "beaty.b-cdn.net",
    "images.collections.yale.edu",
    "nhm.uio.no",
    "nhmo-birds.collectionexplorer.org",
)
MUSEUM_CREDIT_RE = re.compile(
    r"naturalis biodiversity|natural history museum|"
    r"auckland war memorial|cowan tetrapod|"
    r"study skin|preserved specimen|museum collection",
    re.I,
)
NON_PHOTO_FILENAME_RE = re.compile(
    r"map|range|distribution|diagram|illustration|painting|drawing|"
    r"skeleton|skull|specimen|taxidermy|stamp|logo|icon|phylogen|"
    r"cladogram|sonogram|spectrogram|poster|MHNT|\.svg|\.pdf|\.webm|"
    r"egg[\s_]|nest[\s_]|juvenile plumage chart",
    re.I,
)
SKIP_VISUAL_SOURCES = frozenset({"macaulay"})


@dataclass
class SpecimenThresholds:
    min_color_card_bins: int = 8
    max_corner_std: float = 0.08
    max_corner_spread: float = 0.08
    max_corner_chroma: float = 0.12
    max_side: int = 384


def url_host(url: str) -> str:
    try:
        return (urllib.parse.urlparse(url or "").netloc or "").lower()
    except ValueError:
        return ""


def host_has_suffix(host: str, suffix: str) -> bool:
    host = (host or "").lower().split(":")[0].rstrip(".")
    suffix = suffix.lower().rstrip(".")
    return host == suffix or host.endswith("." + suffix)


def is_museum_media_url(url: str) -> bool:
    """True for museum CDNs. Does not match iNaturalist."""
    text = (url or "").lower()
    if not text:
        return False
    host = url_host(text)
    if any(host_has_suffix(host, suffix) for suffix in MUSEUM_HOST_SUFFIXES):
        return True
    return "specify-media." in host


def is_museum_credit(photographer: str = "", credit: str = "") -> bool:
    blob = f"{photographer or ''} {credit or ''}"
    return bool(MUSEUM_CREDIT_RE.search(blob))


def is_non_photo_filename(name: str) -> bool:
    """Maps, diagrams, eggs, skeletons, etc. Useful when ingesting Wikimedia."""
    return bool(NON_PHOTO_FILENAME_RE.search(name or ""))


def _resize_rgb(path: Path, max_side: int) -> Image.Image:
    image = Image.open(path).convert("RGB")
    width, height = image.size
    scale = max_side / max(width, height)
    if scale < 1:
        image = image.resize(
            (max(1, int(width * scale)), max(1, int(height * scale))),
            Image.BILINEAR,
        )
    return image


def _rgb_to_hsv(arr: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    red, green, blue = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    vmax = np.maximum(np.maximum(red, green), blue)
    vmin = np.minimum(np.minimum(red, green), blue)
    delta = vmax - vmin + 1e-6
    hue = np.zeros_like(vmax)
    mask = vmax == red
    hue[mask] = np.mod((green[mask] - blue[mask]) / delta[mask], 6)
    mask = vmax == green
    hue[mask] = (blue[mask] - red[mask]) / delta[mask] + 2
    mask = vmax == blue
    hue[mask] = (red[mask] - green[mask]) / delta[mask] + 4
    sat = delta / (vmax + 1e-6)
    return hue / 6.0, sat, vmax


def color_card_hue_bins(image: Image.Image) -> int:
    """Hue-bin count of high-chroma pixels in a local window. Color cards hit 8+."""
    arr = np.asarray(image, dtype=np.float32) / 255.0
    hue, sat, val = _rgb_to_hsv(arr)
    chroma = (sat > 0.50) & (val > 0.30)
    height, width = hue.shape
    win = max(28, int(0.32 * min(height, width)))
    step = max(8, win // 4)
    best = 0
    for top in range(0, max(1, height - win + 1), step):
        for left in range(0, max(1, width - win + 1), step):
            mask = chroma[top : top + win, left : left + win]
            if int(mask.sum()) < 40:
                continue
            patch = hue[top : top + win, left : left + win][mask]
            hist, _ = np.histogram(patch, bins=12, range=(0.0, 1.0))
            best = max(best, int((hist >= 6).sum()))
    return best


def is_studio_background(
    image: Image.Image,
    thresholds: SpecimenThresholds | None = None,
) -> bool:
    """Low-texture, similar, near-neutral corners (not green bokeh)."""
    thresholds = thresholds or SpecimenThresholds()
    arr = np.asarray(image, dtype=np.float32) / 255.0
    height, width, _ = arr.shape
    margin = max(12, int(0.12 * min(height, width)))
    corners = [
        arr[:margin, :margin],
        arr[:margin, -margin:],
        arr[-margin:, :margin],
        arr[-margin:, -margin:],
    ]
    means = np.array([corner.reshape(-1, 3).mean(axis=0) for corner in corners])
    stds = np.array([float(corner.reshape(-1, 3).std()) for corner in corners])
    chromas = []
    for corner in corners:
        _hue, sat, val = _rgb_to_hsv(corner)
        bright = val > 0.15
        chromas.append(float(sat[bright].mean()) if int(bright.sum()) else 0.0)
    return (
        float(stds.mean()) < thresholds.max_corner_std
        and float(means.std()) < thresholds.max_corner_spread
        and float(np.mean(chromas)) < thresholds.max_corner_chroma
    )


def museum_source_reasons(
    *,
    source_url: str = "",
    photographer: str = "",
    credit: str = "",
) -> list[str]:
    if is_museum_media_url(source_url) or is_museum_credit(photographer, credit):
        return ["specimen_museum_source"]
    return []


def visual_specimen_reasons(
    path: Path,
    thresholds: SpecimenThresholds | None = None,
) -> list[str]:
    thresholds = thresholds or SpecimenThresholds()
    try:
        image = _resize_rgb(path, thresholds.max_side)
    except OSError:
        return []
    if (
        color_card_hue_bins(image) >= thresholds.min_color_card_bins
        and is_studio_background(image, thresholds)
    ):
        return ["specimen_color_card"]
    return []


def specimen_fail_reasons(
    path: Optional[Path] = None,
    *,
    source: str = "",
    source_url: str = "",
    photographer: str = "",
    credit: str = "",
    thresholds: SpecimenThresholds | None = None,
    skip_visual_sources: frozenset[str] | None = None,
) -> list[str]:
    reasons = museum_source_reasons(
        source_url=source_url,
        photographer=photographer,
        credit=credit,
    )
    skip = skip_visual_sources if skip_visual_sources is not None else SKIP_VISUAL_SOURCES
    if (source or "").lower() in skip:
        return reasons
    if path is not None and path.is_file():
        for reason in visual_specimen_reasons(path, thresholds):
            if reason not in reasons:
                reasons.append(reason)
    return reasons
