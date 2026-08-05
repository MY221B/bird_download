"""Regression: --skip-existing must not treat empty image dirs as done."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS = REPO_ROOT / "tools"
sys.path.insert(0, str(TOOLS))

from bird_image_policy import (  # noqa: E402
    MIN_BIRD_IMAGE_BYTES,
    bird_dir_has_acceptable_local_images,
)

BATCH_FETCH = REPO_ROOT / "tools" / "batch_fetch.sh"


def _helper_exit_code(images_root: Path, slug: str) -> int:
    """Mirror the python check embedded in batch_fetch.sh."""
    script = f"""
import sys
from pathlib import Path
sys.path.insert(0, {str(TOOLS)!r})
from bird_image_policy import bird_dir_has_acceptable_local_images
sys.exit(0 if bird_dir_has_acceptable_local_images(Path({str(images_root)!r}) / sys.argv[1]) else 1)
"""
    result = subprocess.run(
        [sys.executable, "-c", script, slug],
        cwd=str(REPO_ROOT),
    )
    return result.returncode


class BatchFetchSkipExistingTests(unittest.TestCase):
    def test_batch_fetch_uses_acceptable_image_guard(self):
        text = BATCH_FETCH.read_text(encoding="utf-8")
        self.assertIn("bird_dir_has_acceptable_local_images", text)
        self.assertIn("bird_has_acceptable_local_images", text)
        # Must not skip solely because the directory exists.
        self.assertNotIn(
            'if [ $SKIP_EXISTING -eq 1 ] && [ -d "images/$slug" ]; then',
            text,
        )

    def test_empty_mkdir_style_dir_is_not_skippable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bird = root / "failed_new_bird"
            for src in ("macaulay", "inaturalist", "wikimedia", "avibase"):
                (bird / src).mkdir(parents=True)
            (bird / "download_metadata.json").write_text(
                '{"macaulay":[],"inaturalist":[],"wikimedia":[],"avibase":[]}',
                encoding="utf-8",
            )
            self.assertFalse(bird_dir_has_acceptable_local_images(bird))
            self.assertEqual(_helper_exit_code(root, "failed_new_bird"), 1)

    def test_tiny_placeholder_only_is_not_skippable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bird = root / "tiny_only"
            src = bird / "macaulay"
            src.mkdir(parents=True)
            (src / "tiny.jpg").write_bytes(b"x" * (MIN_BIRD_IMAGE_BYTES - 1))
            self.assertFalse(bird_dir_has_acceptable_local_images(bird))
            self.assertEqual(_helper_exit_code(root, "tiny_only"), 1)

    def test_acceptable_image_is_skippable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bird = root / "good_bird"
            src = bird / "inaturalist"
            src.mkdir(parents=True)
            (src / "good.jpg").write_bytes(b"y" * MIN_BIRD_IMAGE_BYTES)
            self.assertTrue(bird_dir_has_acceptable_local_images(bird))
            self.assertEqual(_helper_exit_code(root, "good_bird"), 0)


if __name__ == "__main__":
    unittest.main()
