#!/usr/bin/env python3
"""回归：身份解析 / 解析截断 / bird_info 更新不得丢 sounds。"""

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS = PROJECT_ROOT / "tools"
sys.path.insert(0, str(TOOLS))

sys.modules.setdefault("cloudinary", mock.MagicMock())
sys.modules.setdefault("cloudinary.uploader", mock.MagicMock())

import parse_birdreport_table
import process_new_birds
import update_bird_info_in_json


class ParseBirdreportTruncationTests(unittest.TestCase):
    def test_parses_more_than_56_species(self):
        lines = ["科\n"]
        for i in range(1, 61):
            lines.extend(
                [
                    f"{i}\n",
                    f"{4000 + i}\n",
                    f"测试鸟{i}\n",
                    f"Test Bird {i}\n",
                    f"Testus birdus{i}\n",
                    "某目\n",
                    "某科\n",
                ]
            )
        birds = parse_birdreport_table.parse_birdreport_table(lines)
        self.assertEqual(len(birds), 60)
        self.assertEqual(birds[-1]["chinese"], "测试鸟60")


class CanonicalSlugRemapTests(unittest.TestCase):
    def test_merge_remaps_apostrophe_and_hyphen_slug_variants(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "birds.csv"
            all_birds = root / "all_birds.csv"
            uploads = root / "cloudinary_uploads"
            uploads.mkdir()

            all_birds.write_text(
                "# slug,chinese_name,english_name,scientific_name,wikipedia_page\n"
                'japanese_sparrow_hawk,"日本松雀鹰","Japanese Sparrowhawk","Accipiter gularis",Japanese_Sparrowhawk\n'
                'lincoln_s_sparrow,"林肯雀鹀","Lincoln\'s Sparrow","Melospiza lincolnii",Lincoln_s_Sparrow\n',
                encoding="utf-8",
            )
            (uploads / "japanese_sparrow_hawk_cloudinary_urls.json").write_text(
                json.dumps(
                    {
                        "bird_info": {"slug": "japanese_sparrow_hawk"},
                        "macaulay": [{"url": "https://example.com/a.jpg"}],
                        "sounds": [{"url": "https://example.com/a.mp3"}],
                    }
                ),
                encoding="utf-8",
            )
            (uploads / "lincoln_s_sparrow_cloudinary_urls.json").write_text(
                json.dumps(
                    {
                        "bird_info": {"slug": "lincoln_s_sparrow"},
                        "macaulay": [{"url": "https://example.com/b.jpg"}],
                        "sounds": [{"url": "https://example.com/b.mp3"}],
                    }
                ),
                encoding="utf-8",
            )

            csv_path.write_text(
                "# slug,chinese_name,english_name,scientific_name,wikipedia_page\n"
                'japanese_sparrowhawk,"日本松雀鹰","Japanese Sparrowhawk","Accipiter gularis",Japanese_Sparrowhawk\n'
                'lincolns_sparrow,"林肯雀鹀","Lincoln\'s Sparrow","Melospiza lincolnii",Lincolns_Sparrow\n',
                encoding="utf-8",
            )

            def fake_load():
                return _load_csv_map(all_birds)

            with mock.patch.object(process_new_birds, "PROJECT_ROOT", root), mock.patch.object(
                process_new_birds, "load_all_birds_csv", fake_load
            ):
                process_new_birds.merge_with_all_birds_csv(csv_path)

            rows = list(csv.DictReader(
                [l for l in csv_path.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")],
                fieldnames=["slug", "chinese_name", "english_name", "scientific_name", "wikipedia_page"],
            ))
            slugs = {r["slug"] for r in rows}
            self.assertIn("japanese_sparrow_hawk", slugs)
            self.assertIn("lincoln_s_sparrow", slugs)
            self.assertNotIn("japanese_sparrowhawk", slugs)
            self.assertNotIn("lincolns_sparrow", slugs)


class UpdateBirdInfoPreservesSoundsTests(unittest.TestCase):
    def test_update_keeps_sounds_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            uploads = root / "cloudinary_uploads"
            uploads.mkdir()
            jf = uploads / "bluetail_cloudinary_urls.json"
            payload = {
                "bird_info": {"slug": "bluetail", "chinese_name": "红胁蓝尾鸲"},
                "macaulay": [{"url": "https://example.com/m.jpg", "public_id": "m"}],
                "sounds": [{"url": "https://example.com/s.mp3", "original_file": "bluetail_1.mp3"}],
            }
            jf.write_text(json.dumps(payload), encoding="utf-8")

            bird_map = {
                "bluetail": {
                    "chinese_name": "红胁蓝尾鸲",
                    "english_name": "Red-flanked Bluetail",
                    "scientific_name": "Tarsiger cyanurus",
                }
            }
            updated = update_bird_info_in_json.update_json_file(jf, bird_map)
            self.assertTrue(updated)
            data = json.loads(jf.read_text(encoding="utf-8"))
            self.assertEqual(len(data.get("sounds") or []), 1)
            self.assertEqual(data["bird_info"]["english_name"], "Red-flanked Bluetail")
            self.assertEqual(data["macaulay"][0]["url"], "https://example.com/m.jpg")


def _load_csv_map(csv_file: Path) -> dict:
    out = {}
    lines = csv_file.read_text(encoding="utf-8").splitlines()
    data = [l for l in lines if l.strip() and not l.strip().startswith("#")]
    for row in csv.DictReader(
        data,
        fieldnames=["slug", "chinese_name", "english_name", "scientific_name", "wikipedia_page"],
    ):
        slug = row["slug"].strip()
        out[slug] = {
            "chinese_name": row.get("chinese_name", "").strip('"'),
            "english_name": row.get("english_name", "").strip('"'),
            "scientific_name": row.get("scientific_name", "").strip('"'),
            "wikipedia_page": row.get("wikipedia_page", "").strip(),
        }
    return out


if __name__ == "__main__":
    unittest.main()
