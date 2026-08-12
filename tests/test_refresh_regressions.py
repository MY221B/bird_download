import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(module_name, relative_path):
    spec = importlib.util.spec_from_file_location(module_name, REPO_ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RefreshScriptSafetyTests(unittest.TestCase):
    def test_quiz_clean_path_still_reaches_main_repo_push(self):
        for script in [
            REPO_ROOT / "tools" / "weekly_refresh_and_push.sh",
            REPO_ROOT / "tools" / "v2_weekly_refresh_and_push.sh",
        ]:
            with self.subTest(script=script.name):
                text = script.read_text(encoding="utf-8")
                quiz_section, main_repo_section = text.split("# 🔄 推送主仓库改动", 1)

                self.assertNotIn("exit 0", quiz_section)
                self.assertIn('cd "${REPO_ROOT}"', main_repo_section)

    def test_v2_token_remote_is_restored_to_clean_url(self):
        text = (REPO_ROOT / "tools" / "v2_weekly_refresh_and_push.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("restore_quiz_remote", text)
        self.assertIn("trap restore_quiz_remote EXIT", text)
        self.assertIn(
            'git -C "${QUIZ_DIR}" remote set-url origin "https://github.com/MY221B/feather-flash-quiz.git"',
            text,
        )

    def test_min_species_threshold_skips_instead_of_overwriting(self):
        for script in [
            REPO_ROOT / "tools" / "run_weekly_refresh.py",
            REPO_ROOT / "tools" / "run_weekly_refresh_v2.py",
        ]:
            with self.subTest(script=script.name):
                text = script.read_text(encoding="utf-8")

                self.assertNotIn("但仍会继续处理", text)
                self.assertIn("跳过更新以保留上次鸟单", text)
                self.assertIn("continue", text)


class CloudinaryJsonPreservationTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(REPO_ROOT / "tools"))
        cloudinary_module = types.ModuleType("cloudinary")
        cloudinary_uploader = types.ModuleType("cloudinary.uploader")
        cloudinary_module.uploader = cloudinary_uploader
        self.modules = mock.patch.dict(
            sys.modules,
            {
                "cloudinary": cloudinary_module,
                "cloudinary.uploader": cloudinary_uploader,
            },
        )
        self.modules.start()

    def tearDown(self):
        self.modules.stop()
        try:
            sys.path.remove(str(REPO_ROOT / "tools"))
        except ValueError:
            pass

    def test_empty_upload_result_preserves_existing_sources_and_bird_info(self):
        upload_to_cloudinary = load_module(
            "upload_to_cloudinary_for_test", "tools/upload_to_cloudinary.py"
        )

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                output_dir = Path("cloudinary_uploads")
                output_dir.mkdir()
                existing = {
                    "bird_info": {
                        "slug": "test_bird",
                        "chinese_name": "测试鸟",
                        "english_name": "Test Bird",
                        "scientific_name": "Avis testus",
                    },
                    "inaturalist": [{"url": "https://example.com/old.jpg"}],
                    "sounds": [{"url": "https://example.com/sound.mp3"}],
                }
                (output_dir / "test_bird_cloudinary_urls.json").write_text(
                    json.dumps(existing, ensure_ascii=False), encoding="utf-8"
                )

                upload_to_cloudinary.save_results_to_file(
                    "test_bird",
                    {
                        "macaulay": [],
                        "inaturalist": [],
                        "birdphotos": [],
                        "wikimedia": [],
                        "avibase": [],
                    },
                )

                saved = json.loads(
                    (output_dir / "test_bird_cloudinary_urls.json").read_text(
                        encoding="utf-8"
                    )
                )
            finally:
                os.chdir(old_cwd)

        self.assertEqual(saved["bird_info"], existing["bird_info"])
        self.assertEqual(saved["inaturalist"], existing["inaturalist"])
        self.assertEqual(saved["sounds"], existing["sounds"])


class BirdInfoUpdateTests(unittest.TestCase):
    def test_update_bird_info_uses_csv_when_manual_new_bird_file_is_absent(self):
        sys.path.insert(0, str(REPO_ROOT / "tools"))
        old_cwd = os.getcwd()
        try:
            process_new_birds = load_module(
                "process_new_birds_for_test", "tools/process_new_birds.py"
            )
        finally:
            os.chdir(old_cwd)
            try:
                sys.path.remove(str(REPO_ROOT / "tools"))
            except ValueError:
                pass

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            upload_dir = tmp_path / "cloudinary_uploads"
            upload_dir.mkdir()
            json_file = upload_dir / "test_bird_cloudinary_urls.json"
            json_file.write_text('{"inaturalist": [{"url": "https://example.com/old.jpg"}]}', encoding="utf-8")
            csv_file = tmp_path / "birds.csv"
            csv_file.write_text(
                "# slug,chinese_name,english_name,scientific_name,wikipedia_page\n"
                'test_bird,"测试鸟","Test Bird","Avis testus",Test_Bird\n',
                encoding="utf-8",
            )

            with mock.patch.object(process_new_birds, "PROJECT_ROOT", tmp_path):
                self.assertTrue(process_new_birds.update_bird_info(csv_file))

            saved = json.loads(json_file.read_text(encoding="utf-8"))

        self.assertEqual(
            saved["bird_info"],
            {
                "slug": "test_bird",
                "chinese_name": "测试鸟",
                "english_name": "Test Bird",
                "scientific_name": "Avis testus",
            },
        )


if __name__ == "__main__":
    unittest.main()
