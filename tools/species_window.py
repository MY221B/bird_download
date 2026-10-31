#!/usr/bin/env python3
"""Choose a location bird-list window: recent 7d, recent 30d, or 3-year same month."""

from __future__ import annotations

import calendar
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Iterable

SOURCE_RECENT_7D = "recent_7d"
SOURCE_RECENT_30D = "recent_30d"
SOURCE_HISTORICAL_MONTH = "historical_month"

SOURCE_LABELS = {
    SOURCE_RECENT_7D: "近7日鸟类",
    SOURCE_RECENT_30D: "近一月鸟类",
    SOURCE_HISTORICAL_MONTH: "近期可能鸟种",
}

EMPTY_RESULT_MARKERS = ("未返回结果", "都未返回")
HISTORICAL_YEARS_DEFAULT = 3
RECENT_MONTH_DAYS = 30


@dataclass
class SpeciesWindow:
    records: list
    start: date
    end: date
    source: str
    months: tuple[str, ...] = ()
    skipped_recent: bool = False

    @property
    def label(self) -> str:
        return SOURCE_LABELS[self.source]

    @property
    def species_count(self) -> int:
        return len(self.records)

    def record_range_payload(self) -> dict:
        payload = {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "source": self.source,
            "label": self.label,
        }
        if self.source == SOURCE_HISTORICAL_MONTH and self.months:
            payload["months"] = list(self.months)
        return payload


def is_sufficient(count: int, min_species: int) -> bool:
    """Enough species to publish. 10 is not enough when the threshold is 10."""
    return count > min_species


def last_n_days_range(end: date, days: int) -> tuple[date, date]:
    days = max(1, int(days))
    return end - timedelta(days=days - 1), end


def same_month_range(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def historical_same_month_ranges(today: date, years: int = HISTORICAL_YEARS_DEFAULT) -> list[tuple[date, date]]:
    """Past N calendar months matching today.month, newest year first. Excludes this year."""
    years = max(1, int(years))
    ranges = []
    for years_ago in range(1, years + 1):
        ranges.append(same_month_range(today.year - years_ago, today.month))
    return ranges


def recent_source_for_span(start: date, end: date) -> str:
    days = (end - start).days + 1
    if days <= 7:
        return SOURCE_RECENT_7D
    return SOURCE_RECENT_30D


def is_empty_result_error(exc: BaseException) -> bool:
    message = str(exc)
    return any(marker in message for marker in EMPTY_RESULT_MARKERS)


def union_records(groups: Iterable[Iterable]) -> list:
    combined: OrderedDict[tuple, object] = OrderedDict()
    for records in groups:
        for record in records:
            key = (getattr(record, "chinese", None), getattr(record, "scientific", None))
            if key not in combined:
                combined[key] = record
    return list(combined.values())


def write_bird_text(records: Iterable, output_file) -> None:
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            chinese = getattr(record, "chinese", "") or ""
            english = getattr(record, "english", "") or ""
            scientific = getattr(record, "scientific", "") or ""
            line = f"{chinese} {english} {scientific}".strip()
            handle.write(f"{line}\n")


def fetch_records_allow_empty(
    fetch_fn: Callable,
    entry: dict,
    start: date,
    end: date,
    text_file,
    *,
    retries: int = 2,
    sleep_fn=time.sleep,
) -> list:
    """Return records, or [] when the window is empty / all retries fail."""
    attempts = max(1, retries + 1)
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            records = fetch_fn(entry, start, end, text_file)
            return list(records or [])
        except Exception as exc:
            if is_empty_result_error(exc):
                return []
            last_exc = exc
            if attempt < attempts:
                print(f"🔁 抓取失败，第 {attempt}/{attempts} 次尝试，将重试: {exc}")
                sleep_fn(4)
            else:
                print(f"⚠️  时间范围（{start} ~ {end}）{attempts} 次均失败: {exc}")
    if last_exc is not None:
        return []
    return []


def fetch_with_species_fallback(
    *,
    fetch_fn: Callable,
    entry: dict,
    recent_start: date,
    recent_end: date,
    min_species: int,
    text_file,
    today: date | None = None,
    historical_years: int = HISTORICAL_YEARS_DEFAULT,
    retries: int = 2,
    sleep_fn=time.sleep,
    explicit_range: bool = False,
) -> SpeciesWindow | None:
    """
    Pick a publishable window.

    Default cascade:
    1. Recent window (usually 7 days). If species > min_species, publish it.
    2. Else do not publish the recent list; fetch last 30 days.
       Publish 30 days when species > min_species.
    3. Else union the same calendar month across the past `historical_years` years.
       Publish that list even if it is still small, as "近期可能鸟种".
    4. If the historical union is empty, skip (return None) so the frontend keeps
       the previous folder.

    `--start/--end` sets explicit_range=True and skips the cascade.
    """
    today = today or recent_end
    loc_name = entry.get("name") or entry.get("id") or "地点"
    fetch_kwargs = {
        "fetch_fn": fetch_fn,
        "entry": entry,
        "text_file": text_file,
        "retries": retries,
        "sleep_fn": sleep_fn,
    }

    if explicit_range:
        records = fetch_records_allow_empty(start=recent_start, end=recent_end, **fetch_kwargs)
        if not records:
            print(f"❌ {loc_name}: 指定区间（{recent_start} ~ {recent_end}）无记录")
            return None
        write_bird_text(records, text_file)
        return SpeciesWindow(
            records=records,
            start=recent_start,
            end=recent_end,
            source=recent_source_for_span(recent_start, recent_end),
        )

    recent_days = (recent_end - recent_start).days + 1
    print(f"🔎 {loc_name}: 先查近 {recent_days} 天（{recent_start} ~ {recent_end}）")
    records_recent = fetch_records_allow_empty(start=recent_start, end=recent_end, **fetch_kwargs)
    count_recent = len(records_recent)
    print(f"📊 {loc_name} 近窗口去重鸟种: {count_recent}")
    if is_sufficient(count_recent, min_species):
        write_bird_text(records_recent, text_file)
        return SpeciesWindow(
            records=records_recent,
            start=recent_start,
            end=recent_end,
            source=recent_source_for_span(recent_start, recent_end),
        )

    print(
        f"⚠️  {loc_name}: 近窗口 {count_recent} 种 ≤ {min_species}，不写入前端，改查近 {RECENT_MONTH_DAYS} 天"
    )
    if recent_days >= RECENT_MONTH_DAYS:
        records_month = records_recent
        month_start, month_end = recent_start, recent_end
    else:
        month_start, month_end = last_n_days_range(today, RECENT_MONTH_DAYS)
        records_month = fetch_records_allow_empty(start=month_start, end=month_end, **fetch_kwargs)
    count_month = len(records_month)
    print(f"📊 {loc_name} 近{RECENT_MONTH_DAYS}天去重鸟种: {count_month}（{month_start} ~ {month_end}）")
    if is_sufficient(count_month, min_species):
        write_bird_text(records_month, text_file)
        return SpeciesWindow(
            records=records_month,
            start=month_start,
            end=month_end,
            source=SOURCE_RECENT_30D,
            skipped_recent=True,
        )

    print(
        f"⚠️  {loc_name}: 近{RECENT_MONTH_DAYS}天 {count_month} 种 ≤ {min_species}，"
        f"改用过去 {historical_years} 年同月并集"
    )
    month_groups = []
    months: list[str] = []
    successful_ranges: list[tuple[date, date]] = []
    for hist_start, hist_end in historical_same_month_ranges(today, historical_years):
        month_key = f"{hist_start.year:04d}-{hist_start.month:02d}"
        recs = fetch_records_allow_empty(start=hist_start, end=hist_end, **fetch_kwargs)
        print(f"  📅 {month_key}: {len(recs)} 种")
        if recs:
            month_groups.append(recs)
            months.append(month_key)
            successful_ranges.append((hist_start, hist_end))

    records_hist = union_records(month_groups)
    print(f"📊 {loc_name} {historical_years}年同月并集: {len(records_hist)} 种")
    if not records_hist:
        print(f"❌ {loc_name}: 历史同月无记录，跳过写入以保留上次前端数据")
        return None

    write_bird_text(records_hist, text_file)
    hist_start = min(item[0] for item in successful_ranges)
    hist_end = max(item[1] for item in successful_ranges)
    return SpeciesWindow(
        records=records_hist,
        start=hist_start,
        end=hist_end,
        source=SOURCE_HISTORICAL_MONTH,
        months=tuple(months),
        skipped_recent=True,
    )
