"""Optional species-ID gate. Bring your own classifier predictions.

This package does not ship BioCLIP / 懂鸟. Given ranked predictions, decide
whether the photo is the target bird. Default: target (or genus / epithet
alias) must appear in relaxed top-k (k=2).
"""

from __future__ import annotations

from typing import Optional


def id_fail_reason(
    *,
    ok: bool,
    error: str = "",
    looks_like_bird: bool = True,
    relaxed_rank: Optional[int] = None,
    relaxed_top_k: int = 2,
    no_animal_token: str = "未检测",
) -> Optional[str]:
    """Return a reason code, or None if the ID gate passes.

    ``relaxed_rank`` is 1-based index of the first prediction that matches
    the target species, specific epithet, or compatible genus.
    """
    if not ok:
        if no_animal_token and no_animal_token in (error or ""):
            return "id_no_animal"
        return None
    if not looks_like_bird:
        return "id_not_bird"
    if not isinstance(relaxed_rank, int) or relaxed_rank > relaxed_top_k:
        return "id_mismatch"
    return None
