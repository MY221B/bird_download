import json
import unittest
from pathlib import Path

from tools.smart_ebird_lookup import search_taxonomy


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GRASSHOPPER_WARBLER_TAXONOMY = [
    {
        "speciesCode": "grgwar1",
        "comName": "Gray's Grasshopper Warbler",
        "sciName": "Helopsaltes fasciolatus",
    },
    {
        "speciesCode": "migwar",
        "comName": "Middendorff's Grasshopper Warbler",
        "sciName": "Helopsaltes ochotensis",
    },
    {
        "speciesCode": "pagwar1",
        "comName": "Pallas's Grasshopper Warbler",
        "sciName": "Helopsaltes certhiola",
    },
]


class SmartEbirdLookupTest(unittest.TestCase):
    def test_ambiguous_grasshopper_warbler_slugs_use_exact_mappings(self):
        cases = {
            "middendorffs_grasshopper_warbler": "migwar",
            "pallass_grasshopper_warbler": "pagwar1",
        }

        for slug, expected_code in cases.items():
            with self.subTest(slug=slug):
                result = search_taxonomy(GRASSHOPPER_WARBLER_TAXONOMY, slug)
                self.assertIsNotNone(result)
                self.assertEqual(result["code"], expected_code)

    def test_misassigned_grays_recording_only_remains_on_grays_species(self):
        matches = []
        for path in sorted(PROJECT_ROOT.glob("cloudinary_uploads/*grasshopper_warbler_cloudinary_urls.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for sound in data.get("sounds", []):
                source_id = sound.get("attribution", {}).get("source_id")
                if source_id == "601407641":
                    matches.append(path.name)

        self.assertEqual(matches, ["grays_grasshopper_warbler_cloudinary_urls.json"])


if __name__ == "__main__":
    unittest.main()
