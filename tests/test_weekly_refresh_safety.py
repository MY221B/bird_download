import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class Chdir:
    def __init__(self, path):
        self.path = path
        self.previous = None

    def __enter__(self):
        self.previous = Path.cwd()
        os.chdir(self.path)

    def __exit__(self, exc_type, exc, tb):
        os.chdir(self.previous)


def load_upload_module():
    tools_dir = str(REPO_ROOT / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)

    cloudinary = types.ModuleType("cloudinary")
    cloudinary.config = lambda **kwargs: None
    uploader = types.ModuleType("cloudinary.uploader")
    cloudinary.uploader = uploader
    sys.modules.setdefault("cloudinary", cloudinary)
    sys.modules.setdefault("cloudinary.uploader", uploader)

    spec = importlib.util.spec_from_file_location(
        "upload_to_cloudinary_for_test",
        REPO_ROOT / "tools" / "upload_to_cloudinary.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_refresh_module(script_name):
    stubs = {}

    location_utils = types.ModuleType("location_utils")
    location_utils.get_location_birds_path = lambda location, report: Path("/unused")
    stubs["location_utils"] = location_utils

    process_new_birds = types.ModuleType("process_new_birds")
    process_new_birds.load_all_birds_csv = lambda: {}
    for name in [
        "merge_with_all_birds_csv",
        "check_missing_birds",
        "download_birds",
        "check_missing_cloudinary",
        "upload_to_cloudinary",
        "update_bird_info",
        "update_all_birds_csv",
        "generate_html",
        "reorder_new_birds",
    ]:
        setattr(process_new_birds, name, lambda *args, **kwargs: None)
    stubs["process_new_birds"] = process_new_birds

    bird_image_policy = types.ModuleType("bird_image_policy")
    bird_image_policy.bird_dir_has_acceptable_local_images = lambda *args, **kwargs: False
    bird_image_policy.count_acceptable_images_in_bird_dir = lambda *args, **kwargs: 0
    stubs["bird_image_policy"] = bird_image_policy

    fetch_from_birdreport = types.ModuleType("fetch_from_birdreport")
    fetch_from_birdreport.fetch_birds_for_payload = lambda *args, **kwargs: []
    stubs["fetch_from_birdreport"] = fetch_from_birdreport

    auto_sounds_refresh = types.ModuleType("auto_sounds_refresh")
    auto_sounds_refresh.download_and_upload_sounds = lambda *args, **kwargs: None
    auto_sounds_refresh.print_sounds_summary = lambda *args, **kwargs: None
    stubs["auto_sounds_refresh"] = auto_sounds_refresh

    previous = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location(
            f"{script_name}_for_test",
            REPO_ROOT / "tools" / f"{script_name}.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, old_module in previous.items():
            if old_module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old_module


class WeeklyRefreshScriptTests(unittest.TestCase):
    def script_section(self, script_name):
        text = (REPO_ROOT / "tools" / script_name).read_text(encoding="utf-8")
        start = text.index("generate-location-birds-manifest.js")
        end = text.index("# 🔄 推送主仓库改动")
        return text[start:end]

    def test_clean_quiz_does_not_exit_before_main_repo_push(self):
        for script_name in ["weekly_refresh_and_push.sh", "v2_weekly_refresh_and_push.sh"]:
            with self.subTest(script=script_name):
                self.assertNotIn("exit 0", self.script_section(script_name))

    def test_v2_restores_tokenized_quiz_remote_on_exit(self):
        text = (REPO_ROOT / "tools" / "v2_weekly_refresh_and_push.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("ORIGINAL_QUIZ_REMOTE_URL=", text)
        self.assertIn("trap restore_quiz_remote EXIT", text)
        self.assertIn("remote set-url origin \"${ORIGINAL_QUIZ_REMOTE_URL}\"", text)


class UploadMetadataTests(unittest.TestCase):
    def test_empty_partial_upload_results_preserve_existing_urls_and_info(self):
        module = load_upload_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            upload_dir = tmp_path / "cloudinary_uploads"
            upload_dir.mkdir()
            existing = {
                "bird_info": {"slug": "demo_bird", "english_name": "Demo bird"},
                "macaulay": [{"url": "https://example.test/old-macaulay.jpg"}],
                "inaturalist": [{"url": "https://example.test/old-inat.jpg"}],
                "sounds": [{"url": "https://example.test/call.mp3"}],
            }
            (upload_dir / "demo_bird_cloudinary_urls.json").write_text(
                json.dumps(existing),
                encoding="utf-8",
            )

            results = {
                "macaulay": [],
                "inaturalist": [{"url": "https://example.test/new-inat.jpg"}],
                "birdphotos": [],
                "wikimedia": [],
                "avibase": [],
            }
            with Chdir(tmp_path):
                module.save_results_to_file("demo_bird", results)

            saved = json.loads(
                (upload_dir / "demo_bird_cloudinary_urls.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(saved["bird_info"], existing["bird_info"])
            self.assertEqual(saved["macaulay"], existing["macaulay"])
            self.assertEqual(saved["inaturalist"], results["inaturalist"])
            self.assertEqual(saved["sounds"], existing["sounds"])


class LocationCopyTests(unittest.TestCase):
    def test_partial_location_copy_keeps_previous_snapshot(self):
        module = load_refresh_module("run_weekly_refresh_v2")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module.PROJECT_ROOT = root
            module.get_location_birds_path = (
                lambda location, report: root / "location_birds" / location / report
            )

            cloudinary_dir = root / "cloudinary_uploads"
            cloudinary_dir.mkdir()
            (cloudinary_dir / "present_cloudinary_urls.json").write_text(
                "{}", encoding="utf-8"
            )
            old_dir = root / "location_birds" / "park" / "250524"
            old_dir.mkdir(parents=True)
            (old_dir / "old_cloudinary_urls.json").write_text("{}", encoding="utf-8")

            dest_dir, copied, missing = module.copy_json_to_location(
                ["present", "missing"], "park", "250531"
            )

            self.assertEqual(copied, 1)
            self.assertEqual(missing, ["missing"])
            self.assertTrue((dest_dir / "present_cloudinary_urls.json").exists())
            self.assertTrue(old_dir.exists())


if __name__ == "__main__":
    unittest.main()
