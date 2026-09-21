#!/usr/bin/env python3
"""回归：Cloudinary 删除失败时不得清掉本地引用索引。"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS = REPO_ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def load_tool(name: str):
    path = TOOLS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DeleteCloudinaryByListTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_tool("delete_cloudinary_by_list")

    def test_timeout_counts_as_failure_and_exits_nonzero(self):
        def fake_destroy(pid, **kwargs):
            raise TimeoutError("simulated cloudinary timeout")

        succeeded, failed = self.mod.destroy_public_ids(
            ["bird-gallery/a/x", "bird-gallery/b/y"],
            destroy=fake_destroy,
        )
        self.assertEqual(succeeded, [])
        self.assertEqual(len(failed), 2)

        with tempfile.TemporaryDirectory() as tmp:
            lst = Path(tmp) / "list.json"
            lst.write_text(
                json.dumps(
                    {
                        "items": [
                            {"public_id": "bird-gallery/a/x"},
                            {"public_id": "bird-gallery/b/y"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(
                self.mod,
                "destroy_public_ids",
                return_value=([], [("bird-gallery/a/x", "timeout")]),
            ), mock.patch.object(
                self.mod, "ensure_cloudinary_config", return_value="test-cloud"
            ):
                code = self.mod.main(["--file", str(lst)])
        self.assertEqual(code, 1)

    def test_not_found_is_success_for_idempotent_cleanup(self):
        def fake_destroy(pid, **kwargs):
            return {"result": "not found"}

        succeeded, failed = self.mod.destroy_public_ids(
            ["bird-gallery/gone"],
            destroy=fake_destroy,
        )
        self.assertEqual(succeeded, ["bird-gallery/gone"])
        self.assertEqual(failed, [])

    def test_unexpected_status_is_failure(self):
        def fake_destroy(pid, **kwargs):
            return {"result": "error"}

        succeeded, failed = self.mod.destroy_public_ids(
            ["bird-gallery/bad"],
            destroy=fake_destroy,
        )
        self.assertEqual(succeeded, [])
        self.assertEqual(len(failed), 1)

    def test_all_ok_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            lst = Path(tmp) / "list.json"
            lst.write_text(
                json.dumps({"items": [{"public_id": "bird-gallery/ok/1"}]}),
                encoding="utf-8",
            )
            with mock.patch.object(
                self.mod,
                "destroy_public_ids",
                return_value=(["bird-gallery/ok/1"], []),
            ), mock.patch.object(
                self.mod, "ensure_cloudinary_config", return_value="test-cloud"
            ):
                code = self.mod.main(["--file", str(lst)])
        self.assertEqual(code, 0)


class CloudinaryCleanupGuardsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_tool("cloudinary_cleanup")

    def test_sounds_use_video_resource_type(self):
        self.assertEqual(self.mod.resource_type_for_source("sounds"), "video")
        self.assertEqual(self.mod.resource_type_for_source("macaulay"), "image")

    def test_destroy_from_json_reports_failures_and_uses_video_for_sounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            jf = Path(tmp) / "demo_cloudinary_urls.json"
            jf.write_text(
                json.dumps(
                    {
                        "macaulay": [
                            {"public_id": "bird-gallery/demo/macaulay/1"}
                        ],
                        "sounds": [
                            {
                                "public_id": "bird-gallery/demo/sounds/1",
                                "original_file": "demo_1.mp3",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            seen_types = []

            def fake_destroy(pid, **kwargs):
                seen_types.append((pid, kwargs.get("resource_type")))
                if "sounds" in pid:
                    return {"result": "ok"}
                raise TimeoutError("simulated")

            confirmed, failures = self.mod.destroy_from_json(
                jf, destroy=fake_destroy
            )

            self.assertEqual(confirmed, 1)
            self.assertEqual(len(failures), 1)
            self.assertIn(("bird-gallery/demo/sounds/1", "video"), seen_types)
            self.assertIn(("bird-gallery/demo/macaulay/1", "image"), seen_types)

    def test_main_keeps_json_when_any_destroy_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            uploads = root / "cloudinary_uploads"
            uploads.mkdir()
            jf = uploads / "demo_cloudinary_urls.json"
            jf.write_text(
                json.dumps(
                    {
                        "macaulay": [
                            {"public_id": "bird-gallery/demo/macaulay/1"}
                        ]
                    }
                ),
                encoding="utf-8",
            )

            def fake_destroy(pid, **kwargs):
                raise TimeoutError("simulated")

            cwd = Path.cwd()
            try:
                os.chdir(root)
                with mock.patch.object(
                    self.mod, "ensure_cloudinary_config", return_value="test-cloud"
                ), mock.patch.object(
                    self.mod.cloudinary.uploader, "destroy", side_effect=fake_destroy
                ):
                    # destroy_from_json defaults to cloudinary.uploader.destroy
                    code = self.mod.main()
            finally:
                os.chdir(cwd)

            self.assertEqual(code, 1)
            self.assertTrue(jf.exists(), "JSON must remain when destroy fails")
