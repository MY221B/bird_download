import contextlib
import importlib
import io
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

cloudinary_module = types.ModuleType("cloudinary")
cloudinary_uploader_module = types.ModuleType("cloudinary.uploader")
cloudinary_module.uploader = cloudinary_uploader_module
sys.modules.setdefault("cloudinary", cloudinary_module)
sys.modules.setdefault("cloudinary.uploader", cloudinary_uploader_module)


def import_refresh_module(module_name):
    full_name = f"tools.{module_name}"
    sys.modules.pop(full_name, None)
    return importlib.import_module(full_name)


class WeeklyRefreshGuardTest(unittest.TestCase):
    def assert_low_species_location_is_skipped(self, module_name):
        module = import_refresh_module(module_name)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            old_report_dir = tmp_path / "location_birds" / "北京" / "测试点" / "240101"
            old_report_dir.mkdir(parents=True)
            (old_report_dir / "existing.json").write_text("{}", encoding="utf-8")

            args = SimpleNamespace(
                locations=None,
                days=7,
                start="2026-06-01",
                end="2026-06-07",
                min_species=10,
            )

            def fake_location_birds_path(location_name, report_code):
                return tmp_path / "location_birds" / "北京" / location_name / report_code

            with (
                mock.patch.object(module, "parse_args", return_value=args),
                mock.patch.object(
                    module,
                    "load_locations",
                    return_value=[{"id": "test-location", "name": "测试点"}],
                ),
                mock.patch.object(module, "ensure_tmp_dir", return_value=tmp_path / "run"),
                mock.patch.object(module, "get_location_birds_path", side_effect=fake_location_birds_path),
                mock.patch.object(module, "fetch_species_for_location", return_value=[object()]),
                mock.patch.object(module, "write_csv_from_records") as write_csv,
                mock.patch.object(module, "merge_with_all_birds_csv"),
                mock.patch.object(module, "check_missing_birds", return_value=[]),
                mock.patch.object(module, "download_birds", return_value=True),
                mock.patch.object(module, "check_missing_cloudinary", return_value=[]),
                mock.patch.object(module, "upload_to_cloudinary", return_value=True),
                mock.patch.object(module, "update_bird_info"),
                mock.patch.object(module, "download_and_upload_sounds", return_value=([], [])),
                mock.patch.object(module, "load_all_birds_csv", return_value={}),
                mock.patch.object(module, "update_all_birds_csv"),
                mock.patch.object(module, "generate_html"),
                mock.patch.object(module, "reorder_new_birds"),
            ):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    result = module.main()

            self.assertEqual(result, 1)
            self.assertIn("跳过该地点以保留上次报告", output.getvalue())
            write_csv.assert_not_called()
            self.assertTrue(
                old_report_dir.exists(),
                "低于 min-species 的刷新不能删除已有 location_birds 日期目录",
            )

    def test_run_weekly_refresh_skips_low_species_location(self):
        self.assert_low_species_location_is_skipped("run_weekly_refresh")

    def test_run_weekly_refresh_v2_skips_low_species_location(self):
        self.assert_low_species_location_is_skipped("run_weekly_refresh_v2")

    def test_wrappers_do_not_exit_before_main_repo_push(self):
        for script_name in ("weekly_refresh_and_push.sh", "v2_weekly_refresh_and_push.sh"):
            with self.subTest(script=script_name):
                script = (PROJECT_ROOT / "tools" / script_name).read_text(encoding="utf-8")
                main_repo_push = script.index("# 🔄 推送主仓库改动")
                self.assertNotIn(
                    "exit 0",
                    script[:main_repo_push],
                    "clean feather-flash-quiz must not skip main-repo commit/push",
                )

    def test_v2_wrapper_does_not_persist_token_in_remote_url(self):
        script = (PROJECT_ROOT / "tools" / "v2_weekly_refresh_and_push.sh").read_text(encoding="utf-8")
        self.assertNotIn("git remote set-url", script)
        forbidden_message = "remote URL " + "已注入 token"
        self.assertNotIn(forbidden_message, script)


if __name__ == "__main__":
    unittest.main()
