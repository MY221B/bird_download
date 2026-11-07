"""Run quality + specimen filters on one image."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .dead import dead_annotation_reasons
from .quality import (
    QualityMetrics,
    QualityThresholds,
    measure_image,
    quality_fail_reasons,
)
from .specimen import SpecimenThresholds, specimen_fail_reasons


@dataclass
class FilterResult:
    path: str
    reasons: list[str] = field(default_factory=list)
    quality: Optional[dict[str, Any]] = None
    keep: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "keep": self.keep,
            "reasons": list(self.reasons),
            "quality": self.quality,
        }


def evaluate_image(
    path: Path | str,
    *,
    source: str = "",
    source_url: str = "",
    photographer: str = "",
    credit: str = "",
    annotations: list[dict] | None = None,
    alive_or_dead: str = "",
    sha1: str = "",
    cache_dir: Optional[Path] = None,
    quality: bool = True,
    specimen: bool = True,
    dead: bool = True,
    quality_thresholds: QualityThresholds | None = None,
    specimen_thresholds: SpecimenThresholds | None = None,
) -> FilterResult:
    """Return ``keep=False`` when any enabled filter fires."""
    image_path = Path(path)
    reasons: list[str] = []
    metrics: QualityMetrics | None = None
    q_thresholds = quality_thresholds or QualityThresholds()
    if quality:
        metrics = measure_image(
            image_path,
            sha1=sha1,
            cache_dir=cache_dir,
            min_detect_score=q_thresholds.min_detect_score,
        )
        reasons.extend(quality_fail_reasons(metrics, q_thresholds))
    if specimen:
        for reason in specimen_fail_reasons(
            image_path,
            source=source,
            source_url=source_url,
            photographer=photographer,
            credit=credit,
            thresholds=specimen_thresholds,
        ):
            if reason not in reasons:
                reasons.append(reason)
    if dead:
        for reason in dead_annotation_reasons(
            annotations=annotations,
            alive_or_dead=alive_or_dead or None,
        ):
            if reason not in reasons:
                reasons.append(reason)
    return FilterResult(
        path=str(image_path),
        reasons=reasons,
        quality=metrics.to_dict() if metrics is not None else None,
        keep=not reasons,
    )
