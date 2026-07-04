import argparse
import importlib.util
import json
import sys
import types
import unittest
import uuid
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class BirdRecord:
    def __init__(self, chinese, english, scientific=""):
        self.chinese = chinese
        self.english = english
        self.scientific = scientific


def install_fake_dependencies():
    saved = {}
    for name in [
        "location_utils",
        "process_new_birds",
        "bird_image_policy",
        "fetch_from_birdreport",
        "auto_sounds_refresh",
    ]:
        saved[name] = sys.modules.get(name)

    location_utils = types.ModuleType("location_utils")
    location_utils.get_location_birds_path = lambda location, report_code: Path("/unused") / location / report_code

    process_new_birds = types.ModuleType("process_new_birds")
    process_new_birds.load_all_birds_csv = lambda: {}
    process_new_birds.merge_with_all_birds_csv = lambda csv_file: csv_file
    process_new_birds.check_missing_birds = lambda csv_file: []
    process_new_birds.download_birds = lambda csv_file, missing_birds: True
    process_new_birds.check_missing_cloudinary = lambda csv_file: []
    process_new_birds.upload_to_cloudinary = lambda missing_birds, csv_file: True
    process_new_birds.update_bird_info = lambda csv_file: None
    process_new_birds.update_all_birds_csv = lambda: None
    process_new_birds.generate_html = lambda highlight_slugs=None, priority_slugs=None: None
    process_new_birds.reorder_new_birds = lambda csv_file: None

    bird_image_policy = types.ModuleType("bird_image_policy")
    bird_image_policy.bird_dir_has_acceptable_local_images = lambda bird_path: True
    bird_image_policy.count_acceptable_images_in_bird_dir = lambda bird_path: 1

    fetch_from_birdreport = types.ModuleType("fetch_from_birdreport")
    fetch_from_birdreport.fetch_birds_for_payload = lambda payload: []

    auto_sounds_refresh = types.ModuleType("auto_sounds_refresh")
    auto_sounds_refresh.download_and_upload_sounds = lambda bird_slugs, temp_dir: ([], [])
    auto_sounds_refresh.print_sounds_summary = lambda *args, **kwargs: None

    sys.modules["location_utils"] = location_utils
    sys.modules["process_new_birds"] = process_new_birds
    sys.modules["bird_image_policy"] = bird_image_policy
    sys.modules["fetch_from_birdreport"] = fetch_from_birdreport
    sys.modules["auto_sounds_refresh"] = auto_sounds_refresh
    return saved


def restore_dependencies(saved):
    for name, module in saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


def load_refresh_module(script_name):
    saved = install_fake_dependencies()
    module_name = f"{Path(script_name).stem}_{uuid.uuid4().hex}"
    module_path = PROJECT_ROOT / "tools" / script_name
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        restore_dependencies(saved)
        raise
    return module, module_name, saved


def valid_cloudinary_json(root, slug):
    json_path = root / "cloudinary_uploads" / f"{slug}_cloudinary_urls.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps({"macaulay": [{"secure_url": "https://example.test/bird.jpg"}]}),
        encoding="utf-8",
    )


class WeeklyRefreshPublishGuardTests(unittest.TestCase):
    def run_refresh(self, script_name, root, records, min_species):
        module, module_name, saved = load_refresh_module(script_name)
        location_root = root / "feather-flash-quiz" / "location_birds" / "北京"

        module.PROJECT_ROOT = root
        module.TMP_BASE = root / "tmp" / "weekly_refresh"
        module.get_location_birds_path = (
            lambda location, report_code: location_root / location / report_code
        )
        module.parse_args = lambda: argparse.Namespace(
            locations=None,
            days=7,
            start=None,
            end=None,
            min_species=min_species,
        )
        module.load_locations = lambda: [{"id": "test_loc", "name": "Test Preserve"}]
        module.resolve_date_range = lambda entry, args: (
            date(2026, 1, 1),
            date(2026, 1, 7),
        )
        module.fetch_species_for_location = lambda entry, start, end, output_file: records

        try:
            with mock.patch("builtins.print"):
                result = module.main()
            return result
        finally:
            sys.modules.pop(module_name, None)
            restore_dependencies(saved)

    def test_low_species_count_skips_without_deleting_existing_snapshot(self):
        for script_name in ["run_weekly_refresh.py", "run_weekly_refresh_v2.py"]:
            with self.subTest(script_name=script_name):
                with TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    existing = (
                        root
                        / "feather-flash-quiz"
                        / "location_birds"
                        / "北京"
                        / "Test Preserve"
                        / "260101"
                    )
                    existing.mkdir(parents=True)
                    (existing / "old_bird_cloudinary_urls.json").write_text("{}", encoding="utf-8")
                    valid_cloudinary_json(root, "only_bird")

                    result = self.run_refresh(
                        script_name,
                        root,
                        [BirdRecord("测试鸟", "Only Bird", "Avis testus")],
                        min_species=10,
                    )

                    self.assertEqual(result, 1)
                    self.assertTrue(existing.exists())
                    self.assertFalse((existing.parent / "260107").exists())

    def test_missing_publishable_json_skips_without_deleting_existing_snapshot(self):
        for script_name in ["run_weekly_refresh.py", "run_weekly_refresh_v2.py"]:
            with self.subTest(script_name=script_name):
                with TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    existing = (
                        root
                        / "feather-flash-quiz"
                        / "location_birds"
                        / "北京"
                        / "Test Preserve"
                        / "260101"
                    )
                    existing.mkdir(parents=True)
                    (existing / "old_bird_cloudinary_urls.json").write_text("{}", encoding="utf-8")
                    valid_cloudinary_json(root, "bird_one")

                    result = self.run_refresh(
                        script_name,
                        root,
                        [
                            BirdRecord("测试鸟一", "Bird One", "Avis unus"),
                            BirdRecord("测试鸟二", "Bird Two", "Avis duo"),
                        ],
                        min_species=2,
                    )

                    self.assertEqual(result, 1)
                    self.assertTrue(existing.exists())
                    self.assertFalse((existing.parent / "260107").exists())

    def test_valid_refresh_publishes_new_snapshot_and_removes_old_snapshot(self):
        for script_name in ["run_weekly_refresh.py", "run_weekly_refresh_v2.py"]:
            with self.subTest(script_name=script_name):
                with TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    existing = (
                        root
                        / "feather-flash-quiz"
                        / "location_birds"
                        / "北京"
                        / "Test Preserve"
                        / "260101"
                    )
                    existing.mkdir(parents=True)
                    (existing / "old_bird_cloudinary_urls.json").write_text("{}", encoding="utf-8")
                    valid_cloudinary_json(root, "bird_one")
                    valid_cloudinary_json(root, "bird_two")

                    result = self.run_refresh(
                        script_name,
                        root,
                        [
                            BirdRecord("测试鸟一", "Bird One", "Avis unus"),
                            BirdRecord("测试鸟二", "Bird Two", "Avis duo"),
                        ],
                        min_species=2,
                    )

                    new_snapshot = existing.parent / "260107"
                    self.assertEqual(result, 0)
                    self.assertFalse(existing.exists())
                    self.assertTrue((new_snapshot / "bird_one_cloudinary_urls.json").exists())
                    self.assertTrue((new_snapshot / "bird_two_cloudinary_urls.json").exists())


if __name__ == "__main__":
    unittest.main()
