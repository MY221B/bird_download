#!/usr/bin/env python3
"""回归：防止高置信度不足时把鸟声串到错误物种。"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS = PROJECT_ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import auto_sounds_refresh
import process_new_birds
import smart_ebird_lookup
from sync_sounds_to_location_birds import sync_sounds_to_location_json


class NormalizeAndLookupTests(unittest.TestCase):
    def test_normalize_grey_and_hyphen(self):
        self.assertEqual(
            smart_ebird_lookup.normalize_bird_name("Grey-headed Parrotbill"),
            "gray headed parrotbill",
        )
        self.assertEqual(
            smart_ebird_lookup.normalize_bird_name("Greater Sand-Plover"),
            "greater sand plover",
        )

    def test_exact_normalized_english_match(self):
        taxonomy = [
            {
                "speciesCode": "gyhpar3",
                "comName": "Gray-headed Parrotbill",
                "sciName": "Paradoxornis gularis",
            },
            {
                "speciesCode": "reepar3",
                "comName": "Reed Parrotbill",
                "sciName": "Paradoxornis heudei",
            },
        ]
        result = smart_ebird_lookup.search_taxonomy(
            taxonomy,
            "grey_headed_parrotbill",
            english_name="Grey-headed Parrotbill",
            scientific_name="Psittiparus gularis",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["code"], "gyhpar3")

    def test_partial_word_match_fail_closed(self):
        taxonomy = [
            {
                "speciesCode": "magplo1",
                "comName": "Magellanic Plover",
                "sciName": "Pluvianellus socialis",
            },
            {
                "speciesCode": "grsplo",
                "comName": "Greater Sand-Plover",
                "sciName": "Anarhynchus leschenaultii",
            },
        ]
        # 故意不提供可归一化精确命中的英文/学名，且不走 slug 映射
        result = smart_ebird_lookup.search_taxonomy(
            taxonomy,
            "mystery_plover",
            english_name="Mystery Plover",
            scientific_name="Mysteryus ploverus",
        )
        self.assertIsNone(result)

    def test_slug_mappings_for_confused_species(self):
        cases = {
            "grey_headed_parrotbill": "gyhpar3",
            "northern_goshawk": "norgos1",
            "chinese_goshawk": "grfhaw1",
            "greater_sand_plover": "grsplo",
            "lesser_sand_plover": "lessap2",
            "tibetan_sand_plover": "lessap1",
            "chinese_long_tailed_rosefinch": "lotros1",
            "schrencks_bittern": "schbit1",
            "yellow_browed_warbler": "yebwar3",
            "middendorffs_grasshopper_warbler": "migwar",
            "pallass_grasshopper_warbler": "pagwar1",
        }
        for slug, code in cases.items():
            self.assertEqual(
                smart_ebird_lookup.SLUG_TO_CODE_MAPPING[slug],
                code,
                slug,
            )


class GetEbirdCodeGuards(unittest.TestCase):
    def test_fail_closed_without_identity(self):
        with mock.patch.dict(smart_ebird_lookup.SLUG_TO_CODE_MAPPING, {}, clear=True):
            # ensure unmapped slug
            code = auto_sounds_refresh.get_ebird_code("", "", slug="totally_unknown_bird_xyz")
            self.assertIsNone(code)


class UpdateBirdInfoTests(unittest.TestCase):
    def test_updates_from_csv_without_new_birds_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upload = root / "cloudinary_uploads"
            upload.mkdir()
            slug = "demo_warbler"
            json_path = upload / f"{slug}_cloudinary_urls.json"
            json_path.write_text(
                json.dumps({"macaulay": [{"url": "x"}], "sounds": [{"url": "old"}]}),
                encoding="utf-8",
            )
            csv_path = root / "birds.csv"
            csv_path.write_text(
                "#slug,chinese_name,english_name,scientific_name,wikipedia_page\n"
                f"{slug},演示莺,Demo Warbler,Demo demo,\n",
                encoding="utf-8",
            )

            with mock.patch.object(process_new_birds, "PROJECT_ROOT", root):
                ok = process_new_birds.update_bird_info(csv_path)

            self.assertTrue(ok)
            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(data["bird_info"]["english_name"], "Demo Warbler")
            self.assertEqual(data["bird_info"]["scientific_name"], "Demo demo")
            self.assertEqual(data["sounds"][0]["url"], "old")


class SyncSoundsTests(unittest.TestCase):
    def test_sync_when_same_count_but_different_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main = root / "main.json"
            loc = root / "loc.json"
            main.write_text(
                json.dumps({"sounds": [{"url": "correct", "attribution": {"source_id": "1"}}]}),
                encoding="utf-8",
            )
            loc.write_text(
                json.dumps({"sounds": [{"url": "wrong", "attribution": {"source_id": "2"}}]}),
                encoding="utf-8",
            )
            self.assertTrue(sync_sounds_to_location_json(loc, main))
            self.assertEqual(
                json.loads(loc.read_text(encoding="utf-8"))["sounds"][0]["url"],
                "correct",
            )


class PersistedDataGuards(unittest.TestCase):
    def test_misassigned_assets_removed_from_wrong_species(self):
        upload = PROJECT_ROOT / "cloudinary_uploads"
        forbidden = {
            "203692931": {"grey_headed_parrotbill"},
            "291362181": {"northern_goshawk", "chinese_goshawk"},
            "42753541": {
                "greater_sand_plover",
                "lesser_sand_plover",
                "tibetan_sand_plover",
            },
            "251379261": {"chinese_long_tailed_rosefinch"},
            "601407641": {
                "middendorffs_grasshopper_warbler",
                "pallass_grasshopper_warbler",
            },
            "198496211": {"schrencks_bittern"},
        }
        for asset_id, slugs in forbidden.items():
            for slug in slugs:
                path = upload / f"{slug}_cloudinary_urls.json"
                data = json.loads(path.read_text(encoding="utf-8"))
                blob = json.dumps(data.get("sounds") or [])
                self.assertNotIn(asset_id, blob, f"{slug} still has {asset_id}")


if __name__ == "__main__":
    unittest.main()
