"""Specimen-filter unit tests; no network."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from bird_photo_qa import specimen as S


class MuseumSourceTests(unittest.TestCase):
    def test_unimus_is_museum(self) -> None:
        url = "https://api.unimus.no/img-0bbbcc34/web_hent_bilde.php?id=13904415"
        self.assertTrue(S.is_museum_media_url(url))
        self.assertEqual(
            S.museum_source_reasons(source_url=url),
            ["specimen_museum_source"],
        )

    def test_naturalis_host_is_museum(self) -> None:
        self.assertTrue(S.is_museum_media_url("https://medialib.naturalis.nl/file/id/123.jpg"))

    def test_inaturalist_is_not_museum(self) -> None:
        url = "https://www.inaturalist.org/photos/112771555"
        self.assertFalse(S.is_museum_media_url(url))
        self.assertEqual(S.museum_source_reasons(source_url=url), [])

    def test_museum_credit(self) -> None:
        self.assertTrue(S.is_museum_credit("Naturalis Biodiversity Center", ""))
        self.assertFalse(S.is_museum_credit("andrew_thornhill", "andrew_thornhill / iNaturalist / cc-by"))

    def test_non_photo_filename(self) -> None:
        self.assertTrue(S.is_non_photo_filename("Range_map_of_Anas_platyrhynchos.svg"))
        self.assertFalse(S.is_non_photo_filename("Anas_platyrhynchos_male.jpg"))


def _color_card_image() -> Image.Image:
    image = Image.new("RGB", (320, 240), (180, 180, 180))
    draw = ImageDraw.Draw(image)
    palette = [
        (220, 30, 30),
        (30, 180, 40),
        (30, 60, 220),
        (240, 220, 30),
        (20, 200, 200),
        (200, 40, 180),
        (240, 140, 20),
        (80, 40, 160),
        (20, 20, 20),
        (250, 250, 250),
        (120, 80, 40),
        (40, 120, 80),
    ]
    left, top, size = 20, 16, 22
    for idx, color in enumerate(palette):
        row, col = divmod(idx, 4)
        x = left + col * (size + 3)
        y = top + row * (size + 3)
        draw.rectangle((x, y, x + size, y + size), fill=color)
    return image


class VisualSpecimenTests(unittest.TestCase):
    def test_color_card_on_gray_studio_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "card.jpg"
            _color_card_image().save(path, quality=95)
            reasons = S.visual_specimen_reasons(path)
        self.assertEqual(reasons, ["specimen_color_card"])

    def test_green_bokeh_does_not_count_as_studio_card(self) -> None:
        image = Image.new("RGB", (320, 240), (50, 120, 55))
        draw = ImageDraw.Draw(image)
        palette = [
            (220, 30, 30),
            (30, 180, 40),
            (30, 60, 220),
            (240, 220, 30),
            (20, 200, 200),
            (200, 40, 180),
            (240, 140, 20),
            (80, 40, 160),
        ]
        for idx, color in enumerate(palette):
            row, col = divmod(idx, 4)
            x, y = 80 + col * 28, 70 + row * 28
            draw.rectangle((x, y, x + 24, y + 24), fill=color)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bokeh.jpg"
            image.save(path, quality=95)
            self.assertEqual(S.visual_specimen_reasons(path), [])

    def test_macaulay_skips_visual(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "card.jpg"
            _color_card_image().save(path, quality=95)
            self.assertEqual(S.visual_specimen_reasons(path), ["specimen_color_card"])
            self.assertEqual(
                S.specimen_fail_reasons(
                    path,
                    source="macaulay",
                    source_url="https://macaulaylibrary.org/asset/1",
                ),
                [],
            )


if __name__ == "__main__":
    unittest.main()
