"""Unit tests for recent / monthly / historical species-window selection."""

import unittest
from datetime import date
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from species_window import (  # noqa: E402
    SOURCE_HISTORICAL_MONTH,
    SOURCE_RECENT_7D,
    SOURCE_RECENT_30D,
    fetch_with_species_fallback,
    historical_same_month_ranges,
    is_empty_result_error,
    is_sufficient,
    last_n_days_range,
    raise_if_empty_fetch,
    recent_source_for_span,
    same_month_range,
    union_records,
)


class Bird:
    def __init__(self, chinese, scientific=""):
        self.chinese = chinese
        self.english = chinese
        self.scientific = scientific or chinese


def names(window):
    return [record.chinese for record in window.records]


class SpeciesWindowHelperTests(unittest.TestCase):
    def test_ten_species_is_not_enough(self):
        self.assertFalse(is_sufficient(10, 10))
        self.assertFalse(is_sufficient(0, 10))
        self.assertTrue(is_sufficient(11, 10))

    def test_last_n_days_inclusive(self):
        self.assertEqual(
            last_n_days_range(date(2026, 10, 31), 7),
            (date(2026, 10, 25), date(2026, 10, 31)),
        )
        self.assertEqual(
            last_n_days_range(date(2026, 10, 28), 30),
            (date(2026, 9, 29), date(2026, 10, 28)),
        )

    def test_historical_same_month_excludes_current_year(self):
        ranges = historical_same_month_ranges(date(2026, 10, 31), years=3)
        self.assertEqual(
            ranges,
            [
                (date(2025, 10, 1), date(2025, 10, 31)),
                (date(2024, 10, 1), date(2024, 10, 31)),
                (date(2023, 10, 1), date(2023, 10, 31)),
            ],
        )

    def test_february_leap_year(self):
        self.assertEqual(same_month_range(2024, 2), (date(2024, 2, 1), date(2024, 2, 29)))
        self.assertEqual(same_month_range(2023, 2), (date(2023, 2, 1), date(2023, 2, 28)))

    def test_recent_source_for_span(self):
        self.assertEqual(
            recent_source_for_span(date(2026, 10, 22), date(2026, 10, 28)),
            SOURCE_RECENT_7D,
        )
        self.assertEqual(
            recent_source_for_span(date(2026, 9, 29), date(2026, 10, 28)),
            SOURCE_RECENT_30D,
        )

    def test_empty_result_error_detection(self):
        self.assertTrue(is_empty_result_error(RuntimeError("所有搜索词都未返回结果")))
        self.assertTrue(is_empty_result_error(RuntimeError("所有区县查询都未返回结果")))
        self.assertFalse(is_empty_result_error(RuntimeError("签名被拒")))

    def test_union_dedupes_by_chinese_and_scientific(self):
        merged = union_records(
            [
                [Bird("白头鹎", "Pycnonotus sinensis"), Bird("麻雀", "Passer montanus")],
                [Bird("白头鹎", "Pycnonotus sinensis"), Bird("大拟啄木鸟", "Psilopogon virens")],
            ]
        )
        self.assertEqual([bird.chinese for bird in merged], ["白头鹎", "麻雀", "大拟啄木鸟"])

    def test_raise_if_empty_fetch_keeps_api_error(self):
        api_error = ValueError("系统内部异常")
        with self.assertRaises(ValueError) as ctx:
            raise_if_empty_fetch({}, api_error, "所有搜索词都未返回结果")
        self.assertEqual(str(ctx.exception), "系统内部异常")

    def test_raise_if_empty_fetch_uses_empty_marker_without_error(self):
        with self.assertRaises(RuntimeError) as ctx:
            raise_if_empty_fetch({}, None, "所有搜索词都未返回结果")
        self.assertIn("未返回结果", str(ctx.exception))

    def test_raise_if_empty_fetch_noop_when_records_exist(self):
        raise_if_empty_fetch({"x": 1}, ValueError("系统内部异常"), "所有搜索词都未返回结果")


class FetchFallbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.text_file = Path(self.tmp.name) / "birds.txt"
        self.entry = {"name": "西安植物园", "id": "xian_xian_zhiwuyuan"}
        self.today = date(2026, 10, 31)
        self.recent_start = date(2026, 10, 25)
        self.recent_end = date(2026, 10, 31)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, fetch_fn, **kwargs):
        return fetch_with_species_fallback(
            fetch_fn=fetch_fn,
            entry=self.entry,
            recent_start=self.recent_start,
            recent_end=self.recent_end,
            min_species=10,
            text_file=self.text_file,
            today=self.today,
            sleep_fn=lambda _seconds: None,
            **kwargs,
        )

    def test_uses_seven_days_when_over_threshold(self):
        birds = [Bird(f"种{i}") for i in range(11)]

        def fetch_fn(_entry, start, end, _text_file):
            self.assertEqual((start, end), (self.recent_start, self.recent_end))
            return birds

        window = self._run(fetch_fn)
        self.assertEqual(window.source, SOURCE_RECENT_7D)
        self.assertEqual(window.species_count, 11)
        self.assertEqual(window.label, "近7日鸟类")
        self.assertFalse(window.skipped_recent)
        self.assertEqual(
            window.record_range_payload()["source"],
            SOURCE_RECENT_7D,
        )

    def test_seven_days_at_threshold_does_not_publish_and_uses_month(self):
        calls = []

        def fetch_fn(_entry, start, end, _text_file):
            calls.append((start, end))
            span = (end - start).days + 1
            if span <= 7:
                return [Bird(f"近7-{i}") for i in range(10)]
            return [Bird(f"近30-{i}") for i in range(12)]

        window = self._run(fetch_fn)
        self.assertEqual(window.source, SOURCE_RECENT_30D)
        self.assertEqual(window.species_count, 12)
        self.assertEqual(window.start, date(2026, 10, 2))
        self.assertEqual(window.end, date(2026, 10, 31))
        self.assertTrue(window.skipped_recent)
        self.assertEqual(len(calls), 2)
        self.assertNotIn("近7-0", names(window))

    def test_month_at_threshold_falls_back_to_three_year_union(self):
        def fetch_fn(_entry, start, end, _text_file):
            if start >= date(2026, 10, 1):
                return [Bird("白头鹎"), Bird("大拟啄木鸟")]
            if start.year == 2025:
                return [Bird(f"2025-{i}") for i in range(8)] + [Bird("麻雀"), Bird("白头鹎")]
            if start.year == 2024:
                return []
            if start.year == 2023:
                return [Bird("乌鸫"), Bird("麻雀"), Bird("珠颈斑鸠")]
            return []

        window = self._run(fetch_fn)
        self.assertEqual(window.source, SOURCE_HISTORICAL_MONTH)
        self.assertEqual(window.label, "近期可能鸟种")
        self.assertGreater(window.species_count, 10)
        self.assertCountEqual(
            names(window),
            [f"2025-{i}" for i in range(8)] + ["麻雀", "白头鹎", "乌鸫", "珠颈斑鸠"],
        )
        self.assertEqual(window.months, ("2025-10", "2023-10"))
        payload = window.record_range_payload()
        self.assertEqual(payload["label"], "近期可能鸟种")
        self.assertEqual(payload["months"], ["2025-10", "2023-10"])
        self.assertEqual(payload["start"], "2023-10-01")
        self.assertEqual(payload["end"], "2025-10-31")
        self.assertTrue(self.text_file.read_text(encoding="utf-8"))

    def test_skips_write_when_historical_also_empty(self):
        def fetch_fn(_entry, start, end, _text_file):
            if start.year == 2026:
                return [Bird("仅两种A"), Bird("仅两种B")]
            raise RuntimeError("所有搜索词都未返回结果")

        window = self._run(fetch_fn)
        self.assertIsNone(window)

    def test_empty_seven_day_error_still_tries_month(self):
        def fetch_fn(_entry, start, end, _text_file):
            if (end - start).days + 1 <= 7:
                raise RuntimeError("所有搜索词都未返回结果")
            return [Bird(f"月{i}") for i in range(15)]

        window = self._run(fetch_fn)
        self.assertEqual(window.source, SOURCE_RECENT_30D)
        self.assertEqual(window.species_count, 15)

    def test_explicit_range_skips_cascade(self):
        calls = []

        def fetch_fn(_entry, start, end, _text_file):
            calls.append((start, end))
            return [Bird("只有两种A"), Bird("只有两种B")]

        window = self._run(fetch_fn, explicit_range=True)
        self.assertEqual(len(calls), 1)
        self.assertEqual(window.source, SOURCE_RECENT_7D)
        self.assertEqual(window.species_count, 2)

    def test_api_error_on_seven_days_still_uses_month_if_sufficient(self):
        def fetch_fn(_entry, start, end, _text_file):
            if (end - start).days + 1 <= 7:
                raise ValueError("系统内部异常")
            return [Bird(f"月{i}") for i in range(15)]

        window = self._run(fetch_fn, retries=0)
        self.assertEqual(window.source, SOURCE_RECENT_30D)
        self.assertEqual(window.species_count, 15)

    def test_skips_when_recent_windows_are_api_errors(self):
        skip_info = {}
        hist_calls = []

        def fetch_fn(_entry, start, end, _text_file):
            if start.year == 2026:
                raise ValueError("系统内部异常")
            hist_calls.append((start, end))
            return [Bird(f"史{i}") for i in range(20)]

        window = self._run(fetch_fn, retries=0, skip_info=skip_info)
        self.assertIsNone(window)
        self.assertEqual(hist_calls, [])
        self.assertIn("接口失败", skip_info["reason"])
        self.assertFalse(self.text_file.exists())

    def test_skips_historical_when_still_at_or_below_threshold(self):
        skip_info = {}

        def fetch_fn(_entry, start, end, _text_file):
            if start >= date(2026, 10, 1):
                return [Bird("仅两种A"), Bird("仅两种B")]
            if start.year == 2025:
                return [Bird("麻雀"), Bird("白头鹎")]
            return []

        window = self._run(fetch_fn, skip_info=skip_info)
        self.assertIsNone(window)
        self.assertIn("历史同月仍 2 种", skip_info["reason"])
        self.assertFalse(self.text_file.exists())


if __name__ == "__main__":
    unittest.main()
