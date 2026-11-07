from __future__ import annotations

import unittest

from bird_photo_qa.dead import (
    alive_or_dead_from_annotations,
    dead_annotation_reasons,
)


class DeadAnnotationTests(unittest.TestCase):
    def test_dead_by_value_id(self) -> None:
        anns = [{"controlled_attribute_id": 17, "controlled_value_id": 19}]
        self.assertEqual(alive_or_dead_from_annotations(anns), "dead")
        self.assertEqual(dead_annotation_reasons(annotations=anns), ["inat_annotated_dead"])

    def test_alive_by_label(self) -> None:
        anns = [
            {
                "controlled_attribute": {"id": 17, "label": "Alive or Dead"},
                "controlled_value": {"id": 18, "label": "Alive"},
            }
        ]
        self.assertEqual(alive_or_dead_from_annotations(anns), "alive")
        self.assertEqual(dead_annotation_reasons(annotations=anns), [])

    def test_unannotated_passes(self) -> None:
        self.assertIsNone(alive_or_dead_from_annotations([]))
        self.assertEqual(dead_annotation_reasons(annotations=[]), [])
        self.assertEqual(dead_annotation_reasons(annotations=None), [])

    def test_cannot_be_determined_passes(self) -> None:
        anns = [{"controlled_attribute_id": 17, "controlled_value_id": 20}]
        self.assertIsNone(alive_or_dead_from_annotations(anns))
        self.assertEqual(dead_annotation_reasons(annotations=anns), [])

    def test_explicit_status(self) -> None:
        self.assertEqual(dead_annotation_reasons(alive_or_dead="dead"), ["inat_annotated_dead"])
        self.assertEqual(dead_annotation_reasons(alive_or_dead="alive"), [])

    def test_concatenated_attr_val(self) -> None:
        anns = [{"concatenated_attr_val": "17|19"}]
        self.assertEqual(alive_or_dead_from_annotations(anns), "dead")
        self.assertEqual(dead_annotation_reasons(annotations=anns), ["inat_annotated_dead"])
