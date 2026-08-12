import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"


def install_import_stubs():
    process_new_birds = types.ModuleType("process_new_birds")
    process_new_birds.load_all_birds_csv = lambda: {}
    process_new_birds.merge_with_all_birds_csv = lambda *args, **kwargs: None
    process_new_birds.check_missing_birds = lambda *args, **kwargs: ([], {})
    process_new_birds.download_birds = lambda *args, **kwargs: None
    process_new_birds.check_missing_cloudinary = lambda *args, **kwargs: []
    process_new_birds.upload_to_cloudinary = lambda *args, **kwargs: None
    process_new_birds.update_bird_info = lambda *args, **kwargs: None
    process_new_birds.update_all_birds_csv = lambda *args, **kwargs: None
    process_new_birds.generate_html = lambda *args, **kwargs: None
    process_new_birds.reorder_new_birds = lambda *args, **kwargs: None
    sys.modules["process_new_birds"] = process_new_birds

    fetch_from_birdreport = types.ModuleType("fetch_from_birdreport")
    fetch_from_birdreport.fetch_birds_for_payload = lambda *args, **kwargs: []
    sys.modules["fetch_from_birdreport"] = fetch_from_birdreport

    auto_sounds_refresh = types.ModuleType("auto_sounds_refresh")
    auto_sounds_refresh.download_and_upload_sounds = lambda *args, **kwargs: ([], [])
    auto_sounds_refresh.print_sounds_summary = lambda *args, **kwargs: None
    sys.modules["auto_sounds_refresh"] = auto_sounds_refresh


def import_refresh_modules():
    install_import_stubs()
    sys.path.insert(0, str(TOOLS_DIR))
    modules = []
    for module_name in ("run_weekly_refresh", "run_weekly_refresh_v2"):
        sys.modules.pop(module_name, None)
        modules.append(importlib.import_module(module_name))
    return modules


class CopyJsonToLocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.refresh_modules = import_refresh_modules()

    def configure_module(self, module, root):
        module.PROJECT_ROOT = root
        module.get_location_birds_path = (
            lambda location, report_code: root / "location_birds" / location / report_code
        )

    def write_cloudinary_json(self, root, slug):
        path = root / "cloudinary_uploads" / f"{slug}_cloudinary_urls.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")

    def test_complete_copy_removes_old_date_directories(self):
        for module in self.refresh_modules:
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.configure_module(module, root)
                self.write_cloudinary_json(root, "alpha")
                self.write_cloudinary_json(root, "beta")
                old_dir = root / "location_birds" / "Test Park" / "20240101"
                static_dir = root / "location_birds" / "Test Park" / "000000"
                old_dir.mkdir(parents=True)
                static_dir.mkdir(parents=True)

                dest_dir, copied, missing = module.copy_json_to_location(
                    ["alpha", "beta"], "Test Park", "20240522"
                )

                self.assertEqual(copied, 2)
                self.assertEqual(missing, [])
                self.assertTrue(dest_dir.exists())
                self.assertFalse(old_dir.exists())
                self.assertTrue(static_dir.exists())

    def test_incomplete_copy_keeps_old_date_directories(self):
        for module in self.refresh_modules:
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.configure_module(module, root)
                self.write_cloudinary_json(root, "alpha")
                old_dir = root / "location_birds" / "Test Park" / "20240101"
                old_dir.mkdir(parents=True)

                _, copied, missing = module.copy_json_to_location(
                    ["alpha", "missing"], "Test Park", "20240522"
                )

                self.assertEqual(copied, 1)
                self.assertEqual(missing, ["missing"])
                self.assertTrue(old_dir.exists())

    def test_empty_slug_list_keeps_old_date_directories(self):
        for module in self.refresh_modules:
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.configure_module(module, root)
                old_dir = root / "location_birds" / "Test Park" / "20240101"
                old_dir.mkdir(parents=True)

                _, copied, missing = module.copy_json_to_location(
                    [], "Test Park", "20240522"
                )

                self.assertEqual(copied, 0)
                self.assertEqual(missing, [])
                self.assertTrue(old_dir.exists())


if __name__ == "__main__":
    unittest.main()
