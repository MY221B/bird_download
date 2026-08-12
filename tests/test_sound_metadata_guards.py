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


if __name__ == "__main__":
    unittest.main()
