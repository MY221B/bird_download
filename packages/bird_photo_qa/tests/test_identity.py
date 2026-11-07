from __future__ import annotations

import unittest

from bird_photo_qa.identity import id_fail_reason


class IdFailReasonTests(unittest.TestCase):
    def test_keep_relaxed_top2(self) -> None:
        self.assertIsNone(
            id_fail_reason(ok=True, looks_like_bird=True, relaxed_rank=2, relaxed_top_k=2)
        )

    def test_drop_rank3(self) -> None:
        self.assertEqual(
            id_fail_reason(ok=True, looks_like_bird=True, relaxed_rank=3, relaxed_top_k=2),
            "id_mismatch",
        )

    def test_not_bird(self) -> None:
        self.assertEqual(
            id_fail_reason(ok=True, looks_like_bird=False, relaxed_rank=1),
            "id_not_bird",
        )

    def test_error_does_not_drop(self) -> None:
        self.assertIsNone(id_fail_reason(ok=False, error="timeout"))

    def test_no_animal(self) -> None:
        self.assertEqual(id_fail_reason(ok=False, error="未检测到目标"), "id_no_animal")
