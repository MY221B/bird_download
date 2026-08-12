"""Regression: gallery must not expose sounds as deletable photos; local delete must not fuzzy-wipe siblings."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS = REPO_ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def load_tool(name: str):
    path = TOOLS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class GalleryExcludesSoundsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gallery = load_tool("update_gallery_from_cloudinary")

    def test_build_html_does_not_emit_sound_cards_or_pids(self):
        sound_pid = "bird-gallery/demo_bird/sounds/demo_bird_111"
        photo_pid = "bird-gallery/demo_bird/macaulay/demo_bird_1"
        data = {
            "demo_bird": {
                "bird_info": {
                    "chinese": "测试鸟",
                    "english": "Demo Bird",
                    "scientific": "Demo demo",
                },
                "macaulay": [
                    {
                        "url": (
                            "https://res.cloudinary.com/dzor6lhz8/image/upload/"
                            f"v1/{photo_pid}.jpg"
                        ),
                        "public_id": photo_pid,
                        "original_file": "demo_bird_1.jpg",
                        "width": 100,
                        "height": 100,
                        "bytes": 1024,
                        "format": "jpg",
                    }
                ],
                "inaturalist": [],
                "birdphotos": [],
                "wikimedia": [],
                "avibase": [],
                "sounds": [
                    {
                        "url": (
                            "https://res.cloudinary.com/dzor6lhz8/video/upload/"
                            f"v1/{sound_pid}.mp3"
                        ),
                        "public_id": sound_pid,
                        "original_file": "demo_bird_111.mp3",
                        "format": "mp3",
                        "bytes": 2048,
                    }
                ],
            }
        }
        html = self.gallery.build_html(data, ["demo_bird"])
        self.assertIn(photo_pid, html)
        self.assertNotIn(sound_pid, html)
        self.assertNotIn(">sounds<", html.lower())
        self.assertNotIn("demo_bird_111.mp3", html)
        # 统计应只计图片，不含叫声
        self.assertIn('<div class="stat-number">1</div><div class="stat-label">总图片数</div>', html)

    def test_image_source_keys_exclude_sounds(self):
        self.assertIn("macaulay", self.gallery.IMAGE_SOURCE_KEYS)
        self.assertNotIn("sounds", self.gallery.IMAGE_SOURCE_KEYS)
        self.assertNotIn("bird_info", self.gallery.IMAGE_SOURCE_KEYS)


class LocalDeleteExactOnlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_tool("delete_local_images_by_list")

    def test_missing_exact_file_does_not_delete_substring_siblings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local_dir = root / "demo_bird" / "macaulay"
            local_dir.mkdir(parents=True)
            keep_10 = local_dir / "demo_bird_10.jpg"
            keep_11 = local_dir / "demo_bird_11.jpg"
            keep_2 = local_dir / "demo_bird_2.jpg"
            for p in (keep_10, keep_11, keep_2):
                p.write_bytes(b"x" * 64)

            buf = io.StringIO()
            with redirect_stdout(buf):
                self.mod.delete_local_images(
                    ["bird-gallery/demo_bird/macaulay/demo_bird_1"],
                    images_dir=root,
                )

            self.assertTrue(keep_10.exists())
            self.assertTrue(keep_11.exists())
            self.assertTrue(keep_2.exists())
            self.assertNotIn("模糊匹配", buf.getvalue())

    def test_exact_match_still_deletes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local_dir = root / "demo_bird" / "macaulay"
            local_dir.mkdir(parents=True)
            target = local_dir / "demo_bird_1.jpg"
            sibling = local_dir / "demo_bird_10.jpg"
            target.write_bytes(b"y" * 64)
            sibling.write_bytes(b"z" * 64)

            self.mod.delete_local_images(
                ["bird-gallery/demo_bird/macaulay/demo_bird_1"],
                images_dir=root,
            )

            self.assertFalse(target.exists())
            self.assertTrue(sibling.exists())


if __name__ == "__main__":
    unittest.main()
