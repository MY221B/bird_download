#!/usr/bin/env python3
"""回归：Cloudinary JSON 合并不得用空来源覆盖已有图片。"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS = PROJECT_ROOT / "tools"
sys.path.insert(0, str(TOOLS))

# upload_to_cloudinary 在 import 时会拉取 cloudinary；测试环境可能未安装。
sys.modules.setdefault("cloudinary", mock.MagicMock())
sys.modules.setdefault("cloudinary.uploader", mock.MagicMock())

import upload_to_cloudinary


class MergeUploadResultsTests(unittest.TestCase):
    def test_empty_source_does_not_wipe_existing_photos(self):
        existing = {
            "bird_info": {
                "slug": "demo_bird",
                "chinese_name": "演示鸟",
                "english_name": "Demo Bird",
                "scientific_name": "Demo demo",
            },
            "macaulay": [{"url": "https://example.com/m1.jpg", "public_id": "m1"}],
            "inaturalist": [{"url": "https://example.com/i1.jpg", "public_id": "i1"}],
            "birdphotos": [],
            "wikimedia": [],
            "avibase": [],
            "sounds": [{"url": "https://example.com/s1.mp3"}],
        }
        results = {
            "bird_info": {
                "slug": "demo_bird",
                "chinese_name": "演示鸟",
                "english_name": "Demo Bird",
                "scientific_name": "Demo demo",
            },
            "macaulay": [],
            "inaturalist": [],
            "birdphotos": [{"url": "https://example.com/b1.jpg", "public_id": "b1"}],
            "wikimedia": [],
            "avibase": [],
        }

        merged = upload_to_cloudinary.merge_upload_results(existing, results)

        self.assertEqual(merged["macaulay"], existing["macaulay"])
        self.assertEqual(merged["inaturalist"], existing["inaturalist"])
        self.assertEqual(merged["birdphotos"], results["birdphotos"])
        self.assertEqual(merged["sounds"], existing["sounds"])
        self.assertEqual(merged["bird_info"]["slug"], "demo_bird")

    def test_missing_bird_info_preserves_existing(self):
        existing = {
            "bird_info": {
                "slug": "demo_bird",
                "chinese_name": "演示鸟",
                "english_name": "Demo Bird",
                "scientific_name": "Demo demo",
            },
            "macaulay": [{"url": "https://example.com/m1.jpg"}],
        }
        results = {
            "macaulay": [{"url": "https://example.com/m2.jpg"}],
            "inaturalist": [],
            "birdphotos": [],
            "wikimedia": [],
            "avibase": [],
        }

        merged = upload_to_cloudinary.merge_upload_results(existing, results)

        self.assertEqual(merged["bird_info"], existing["bird_info"])
        self.assertEqual(merged["macaulay"], results["macaulay"])

    def test_new_upload_can_replace_non_empty_source(self):
        existing = {
            "macaulay": [{"url": "https://example.com/old.jpg"}],
        }
        results = {
            "macaulay": [
                {"url": "https://example.com/new1.jpg"},
                {"url": "https://example.com/new2.jpg"},
            ],
            "inaturalist": [],
            "birdphotos": [],
            "wikimedia": [],
            "avibase": [],
        }

        merged = upload_to_cloudinary.merge_upload_results(existing, results)
        self.assertEqual(len(merged["macaulay"]), 2)
        self.assertEqual(merged["macaulay"][0]["url"], "https://example.com/new1.jpg")


class SaveResultsToFileTests(unittest.TestCase):
    def test_save_merges_on_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            uploads = tmp_path / "cloudinary_uploads"
            uploads.mkdir()
            bird = "demo_bird"
            existing = {
                "bird_info": {"slug": bird, "chinese_name": "演示鸟"},
                "macaulay": [{"url": "https://example.com/m1.jpg"}],
                "inaturalist": [{"url": "https://example.com/i1.jpg"}],
                "sounds": [{"url": "https://example.com/s1.mp3"}],
            }
            (uploads / f"{bird}_cloudinary_urls.json").write_text(
                json.dumps(existing, ensure_ascii=False),
                encoding="utf-8",
            )

            results = {
                "bird_info": {"slug": bird, "chinese_name": "演示鸟"},
                "macaulay": [],
                "inaturalist": [],
                "birdphotos": [{"url": "https://example.com/b1.jpg"}],
                "wikimedia": [],
                "avibase": [],
            }

            old_cwd = os.getcwd()
            try:
                os.chdir(tmp_path)
                upload_to_cloudinary.save_results_to_file(bird, results)
                data = json.loads(
                    (uploads / f"{bird}_cloudinary_urls.json").read_text(encoding="utf-8")
                )
            finally:
                os.chdir(old_cwd)

        self.assertEqual(data["macaulay"], existing["macaulay"])
        self.assertEqual(data["inaturalist"], existing["inaturalist"])
        self.assertEqual(data["birdphotos"], results["birdphotos"])
        self.assertEqual(data["sounds"], existing["sounds"])


if __name__ == "__main__":
    unittest.main()
