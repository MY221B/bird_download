import sys
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from smart_ebird_lookup import search_taxonomy  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
