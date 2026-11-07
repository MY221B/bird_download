"""Bird photo quality filters: subject size, blur, people scenes, museum specimens, annotated-dead."""

from .dead import alive_or_dead_from_annotations, dead_annotation_reasons
from .identity import id_fail_reason
from .pipeline import FilterResult, evaluate_image
from .quality import (
    QualityMetrics,
    QualityThresholds,
    detector_available,
    measure_image,
    quality_fail_reasons,
)
from .specimen import (
    SpecimenThresholds,
    is_museum_credit,
    is_museum_media_url,
    is_non_photo_filename,
    specimen_fail_reasons,
)

__all__ = [
    "FilterResult",
    "QualityMetrics",
    "QualityThresholds",
    "SpecimenThresholds",
    "alive_or_dead_from_annotations",
    "dead_annotation_reasons",
    "detector_available",
    "evaluate_image",
    "id_fail_reason",
    "is_museum_credit",
    "is_museum_media_url",
    "is_non_photo_filename",
    "measure_image",
    "quality_fail_reasons",
    "specimen_fail_reasons",
]
