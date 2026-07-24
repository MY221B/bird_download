import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = PROJECT_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import auto_sounds_refresh
import process_new_birds
from smart_ebird_lookup import SLUG_TO_CODE_MAPPING, smart_get_ebird_code


class SoundMetadataGuardTest(unittest.TestCase):
    def test_csv_metadata_is_written_without_manual_new_birds_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upload_dir = root / "cloudinary_uploads"
            upload_dir.mkdir()
            csv_file = root / "birds.csv"
            csv_file.write_text(
                "# slug,chinese_name,english_name,scientific_name,wikipedia_page\n"
                'band_bellied_crake,"斑胁田鸡","Band-bellied Crake",'
                '"Zapornia paykullii",Band-bellied_Crake\n',
                encoding="utf-8",
            )
            json_file = upload_dir / "band_bellied_crake_cloudinary_urls.json"
            original_sound = {"attribution": {"source_id": "existing"}}
            json_file.write_text(
                json.dumps(
                    {
                        "macaulay": [{"public_id": "existing-photo"}],
                        "sounds": [original_sound],
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.object(process_new_birds, "PROJECT_ROOT", root):
                self.assertTrue(process_new_birds.update_bird_info(csv_file))

            data = json.loads(json_file.read_text(encoding="utf-8"))
            self.assertEqual(
                data["bird_info"],
                {
                    "slug": "band_bellied_crake",
                    "chinese_name": "斑胁田鸡",
                    "english_name": "Band-bellied Crake",
                    "scientific_name": "Zapornia paykullii",
                },
            )
            self.assertEqual(data["macaulay"], [{"public_id": "existing-photo"}])
            self.assertEqual(data["sounds"], [original_sound])

    def test_missing_identity_does_not_use_fuzzy_slug_lookup(self):
        with mock.patch.object(
            auto_sounds_refresh,
            "smart_get_ebird_code",
            return_value="corcra",
        ) as smart_lookup:
            code = auto_sounds_refresh.get_ebird_code(
                "",
                "",
                slug="band_bellied_crake",
            )

        self.assertIsNone(code)
        smart_lookup.assert_not_called()

    def test_exact_slug_mapping_still_handles_legacy_json(self):
        with mock.patch.object(
            auto_sounds_refresh,
            "smart_get_ebird_code",
        ) as smart_lookup:
            code = auto_sounds_refresh.get_ebird_code(
                "",
                "",
                slug="red_necked_phalarope",
            )

        self.assertEqual(code, "renpha")
        smart_lookup.assert_not_called()

    def test_known_ambiguous_slugs_have_exact_mappings(self):
        expected = {
            "middendorffs_grasshopper_warbler": "migwar",
            "pallass_grasshopper_warbler": "pagwar1",
            "schrencks_bittern": "schbit1",
            "yellow_browed_warbler": "yebwar3",
            "blunt_winged_warbler": "blwwar1",
            "eastern_grass_owl": "ausgro1",
        }
        for slug, code in expected.items():
            with self.subTest(slug=slug):
                self.assertEqual(SLUG_TO_CODE_MAPPING[slug], code)
                self.assertEqual(
                    smart_get_ebird_code(slug=slug, english_name="", scientific_name=""),
                    code,
                )


class PersistedSoundMixupGuardTest(unittest.TestCase):
    def test_wrong_shared_sounds_are_removed_from_misrouted_species(self):
        cases = {
            "schrencks_bittern": "198496211",
            "yellow_browed_warbler": "205371",
            "blunt_winged_warbler": "361083721",
            "eastern_grass_owl": "271631421",
            "middendorffs_grasshopper_warbler": "601407641",
            "pallass_grasshopper_warbler": "601407641",
        }
        for slug, bad_asset in cases.items():
            with self.subTest(slug=slug):
                path = PROJECT_ROOT / "cloudinary_uploads" / f"{slug}_cloudinary_urls.json"
                data = json.loads(path.read_text(encoding="utf-8"))
                blob = json.dumps(data.get("sounds") or [], ensure_ascii=False)
                self.assertNotIn(bad_asset, blob)
                bird_info = data.get("bird_info") or {}
                self.assertEqual(bird_info.get("slug"), slug)
                self.assertTrue(bird_info.get("english_name"))
                self.assertTrue(bird_info.get("scientific_name"))

        eurasian = json.loads(
            (
                PROJECT_ROOT
                / "cloudinary_uploads"
                / "eurasian_bittern_cloudinary_urls.json"
            ).read_text(encoding="utf-8")
        )
        self.assertIn("198496211", json.dumps(eurasian.get("sounds") or []))

        grays = json.loads(
            (
                PROJECT_ROOT
                / "cloudinary_uploads"
                / "grays_grasshopper_warbler_cloudinary_urls.json"
            ).read_text(encoding="utf-8")
        )
        self.assertIn("601407641", json.dumps(grays.get("sounds") or []))


if __name__ == "__main__":
    unittest.main()
