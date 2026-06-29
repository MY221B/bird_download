import argparse
import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = PROJECT_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

cloudinary_stub = types.ModuleType("cloudinary")
cloudinary_uploader_stub = types.ModuleType("cloudinary.uploader")
cloudinary_stub.uploader = cloudinary_uploader_stub
sys.modules.setdefault("cloudinary", cloudinary_stub)
sys.modules.setdefault("cloudinary.uploader", cloudinary_uploader_stub)

import location_utils
import run_weekly_refresh
import run_weekly_refresh_v2


class WeeklyRefreshGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.location = "Test Location"
        self.city = "Test City"

        self.project_root_patcher = mock.patch.object(location_utils, "PROJECT_ROOT", self.root)
        self.location_cache_patcher = mock.patch.object(
            location_utils,
            "_location_to_city_cache",
            {self.location: self.city},
        )
        self.project_root_patcher.start()
        self.location_cache_patcher.start()
        self.addCleanup(self.project_root_patcher.stop)
        self.addCleanup(self.location_cache_patcher.stop)

    def _location_root(self):
        return self.root / "feather-flash-quiz" / "location_birds" / self.city / self.location

    def _write_cloudinary_json(self, slug):
        cloudinary_dir = self.root / "cloudinary_uploads"
        cloudinary_dir.mkdir(parents=True, exist_ok=True)
        payload = {"macaulay": [{"url": f"https://example.test/{slug}.jpg"}]}
        (cloudinary_dir / f"{slug}_cloudinary_urls.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def _assert_missing_json_keeps_old_snapshot(self, module):
        old_dir = self._location_root() / "240101"
        old_dir.mkdir(parents=True, exist_ok=True)
        (old_dir / "old.json").write_text("{}", encoding="utf-8")
        self._write_cloudinary_json("bird_a")

        with mock.patch.object(module, "PROJECT_ROOT", self.root):
            dest_dir, copied, missing = module.copy_json_to_location(
                ["bird_a", "bird_b"],
                self.location,
                "240201",
            )

        self.assertIsNone(dest_dir)
        self.assertEqual(copied, 0)
        self.assertEqual(missing, ["bird_b"])
        self.assertTrue(old_dir.exists())
        self.assertFalse((self._location_root() / "240201").exists())

    def test_missing_json_keeps_old_snapshot_in_both_refresh_scripts(self):
        for module in (run_weekly_refresh, run_weekly_refresh_v2):
            with self.subTest(module=module.__name__):
                self._assert_missing_json_keeps_old_snapshot(module)

    def test_complete_json_set_replaces_old_snapshot_in_v2(self):
        old_dir = self._location_root() / "240101"
        old_dir.mkdir(parents=True, exist_ok=True)
        (old_dir / "old.json").write_text("{}", encoding="utf-8")
        static_dir = self._location_root() / "000000"
        static_dir.mkdir(parents=True, exist_ok=True)
        self._write_cloudinary_json("bird_a")
        self._write_cloudinary_json("bird_b")

        with mock.patch.object(run_weekly_refresh_v2, "PROJECT_ROOT", self.root):
            dest_dir, copied, missing = run_weekly_refresh_v2.copy_json_to_location(
                ["bird_a", "bird_b"],
                self.location,
                "240201",
            )

        self.assertEqual(dest_dir, self._location_root() / "240201")
        self.assertEqual(copied, 2)
        self.assertEqual(missing, [])
        self.assertFalse(old_dir.exists())
        self.assertTrue(static_dir.exists())
        self.assertTrue((dest_dir / "bird_a_cloudinary_urls.json").exists())
        self.assertTrue((dest_dir / "bird_b_cloudinary_urls.json").exists())

    def _assert_low_species_skips_publish(self, module):
        records = [
            SimpleNamespace(chinese="A", english="Bird A", scientific="A a"),
            SimpleNamespace(chinese="B", english="Bird B", scientific="B b"),
        ]
        args = argparse.Namespace(
            locations=None,
            days=7,
            start=None,
            end="2026-06-29",
            min_species=10,
        )
        run_dir = self.root / "tmp" / "weekly_refresh" / "case"
        stdout = io.StringIO()

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(module, "parse_args", return_value=args))
            stack.enter_context(
                mock.patch.object(
                    module,
                    "load_locations",
                    return_value=[{"id": "test", "name": self.location}],
                )
            )
            stack.enter_context(mock.patch.object(module, "ensure_tmp_dir", return_value=run_dir))
            stack.enter_context(
                mock.patch.object(module, "fetch_species_for_location", return_value=records)
            )
            merge = stack.enter_context(mock.patch.object(module, "merge_with_all_birds_csv"))
            write_csv = stack.enter_context(mock.patch.object(module, "write_csv_from_records"))
            copy_json = stack.enter_context(mock.patch.object(module, "copy_json_to_location"))
            stack.enter_context(mock.patch.object(module, "load_all_birds_csv", return_value={}))
            stack.enter_context(mock.patch.object(module, "download_birds", return_value=True))
            stack.enter_context(mock.patch.object(module, "upload_to_cloudinary", return_value=True))
            stack.enter_context(mock.patch.object(module, "generate_html"))
            stack.enter_context(mock.patch.object(module, "update_all_birds_csv"))
            stack.enter_context(mock.patch.object(module, "reorder_new_birds"))
            stack.enter_context(contextlib.redirect_stdout(stdout))

            result = module.main()

        self.assertEqual(result, 1)
        self.assertIn("跳过更新", stdout.getvalue())
        merge.assert_not_called()
        write_csv.assert_not_called()
        copy_json.assert_not_called()

    def test_low_species_skips_publish_in_both_refresh_scripts(self):
        for module in (run_weekly_refresh, run_weekly_refresh_v2):
            with self.subTest(module=module.__name__):
                self._assert_low_species_skips_publish(module)


if __name__ == "__main__":
    unittest.main()
