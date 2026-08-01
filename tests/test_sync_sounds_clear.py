#!/usr/bin/env python3
"""Regression: clearing main sounds must propagate to location JSON."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from sync_sounds_to_location_birds import sync_sounds_to_location_json  # noqa: E402


class SyncSoundsClearTests(unittest.TestCase):
    def test_empty_main_sounds_clears_location_wrong_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main = root / "main.json"
            loc = root / "loc.json"
            main.write_text(json.dumps({"sounds": []}), encoding="utf-8")
            loc.write_text(
                json.dumps(
                    {
                        "sounds": [
                            {
                                "url": "https://example.com/wrong.mp3",
                                "attribution": {"source_id": "203692931"},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            self.assertTrue(sync_sounds_to_location_json(loc, main))
            self.assertEqual(json.loads(loc.read_text(encoding="utf-8"))["sounds"], [])

    def test_missing_sounds_key_on_main_does_not_wipe_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main = root / "main.json"
            loc = root / "loc.json"
            main.write_text(json.dumps({"macaulay": []}), encoding="utf-8")
            loc.write_text(
                json.dumps({"sounds": [{"url": "stale"}]}),
                encoding="utf-8",
            )

            self.assertFalse(sync_sounds_to_location_json(loc, main))
            self.assertEqual(
                json.loads(loc.read_text(encoding="utf-8"))["sounds"][0]["url"],
                "stale",
            )

    def test_noop_when_both_already_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main = root / "main.json"
            loc = root / "loc.json"
            main.write_text(json.dumps({"sounds": []}), encoding="utf-8")
            loc.write_text(json.dumps({"sounds": []}), encoding="utf-8")

            self.assertFalse(sync_sounds_to_location_json(loc, main))

    def test_same_count_different_content_still_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main = root / "main.json"
            loc = root / "loc.json"
            main.write_text(
                json.dumps({"sounds": [{"url": "correct", "attribution": {"source_id": "1"}}]}),
                encoding="utf-8",
            )
            loc.write_text(
                json.dumps({"sounds": [{"url": "wrong", "attribution": {"source_id": "2"}}]}),
                encoding="utf-8",
            )

            self.assertTrue(sync_sounds_to_location_json(loc, main))
            self.assertEqual(
                json.loads(loc.read_text(encoding="utf-8"))["sounds"][0]["url"],
                "correct",
            )


if __name__ == "__main__":
    unittest.main()
