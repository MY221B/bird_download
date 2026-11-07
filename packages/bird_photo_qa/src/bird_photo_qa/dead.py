"""Drop photos whose iNaturalist observation is annotated Dead.

Does not guess from pixels. Unannotated observations are kept.
Term 17 = Alive or Dead; value 19 = Dead, 18 = Alive.
"""

from __future__ import annotations

from typing import Any, Optional

INAT_ALIVE_DEAD_TERM = 17
INAT_ALIVE_VALUE = 18
INAT_DEAD_VALUE = 19


def alive_or_dead_from_annotations(annotations: Optional[list[dict[str, Any]]]) -> Optional[str]:
    """Return ``alive``, ``dead``, or None if not annotated / cannot tell."""
    for row in annotations or []:
        attr = row.get("controlled_attribute") or {}
        attr_id = int(row.get("controlled_attribute_id") or attr.get("id") or 0)
        attr_label = str(attr.get("label") or "").strip().lower()
        concat = str(row.get("concatenated_attr_val") or "")
        is_alive_dead = (
            attr_id == INAT_ALIVE_DEAD_TERM
            or attr_label == "alive or dead"
            or concat.startswith(f"{INAT_ALIVE_DEAD_TERM}|")
        )
        if not is_alive_dead:
            continue
        value = row.get("controlled_value") or {}
        value_id = int(row.get("controlled_value_id") or value.get("id") or 0)
        value_label = str(value.get("label") or "").strip().lower()
        if value_id == INAT_DEAD_VALUE or value_label == "dead" or concat.endswith(f"|{INAT_DEAD_VALUE}"):
            return "dead"
        if value_id == INAT_ALIVE_VALUE or value_label == "alive" or concat.endswith(f"|{INAT_ALIVE_VALUE}"):
            return "alive"
    return None


def dead_annotation_reasons(
    *,
    annotations: Optional[list[dict[str, Any]]] = None,
    alive_or_dead: Optional[str] = None,
) -> list[str]:
    status = (alive_or_dead or "").strip().lower() or alive_or_dead_from_annotations(annotations)
    if status == "dead":
        return ["inat_annotated_dead"]
    return []
