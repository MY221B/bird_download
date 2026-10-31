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

FETCH_OK = "ok"
FETCH_EMPTY = "empty"
FETCH_ERROR = "error"


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


@dataclass
class FetchOutcome:
    status: str
    records: list | None = None
    error: BaseException | None = None

    def __post_init__(self) -> None:
        if self.records is None:
            self.records = []

    @property
    def known(self) -> bool:
        return self.status != FETCH_ERROR


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


def raise_if_empty_fetch(combined, last_error: BaseException | None, empty_message: str) -> None:
    """Re-raise a real API error instead of disguising it as an empty window."""
    if combined:
        return
    if last_error is not None:
        raise last_error
    raise RuntimeError(empty_message)


def is_known_insufficient(outcome: FetchOutcome, min_species: int) -> bool:
    return outcome.known and not is_sufficient(len(outcome.records), min_species)


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
) -> FetchOutcome:
    """Fetch one window. Empty results stay empty; API errors stay errors."""
    attempts = max(1, retries + 1)
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            records = fetch_fn(entry, start, end, text_file)
            return FetchOutcome(status=FETCH_OK, records=list(records or []))
        except Exception as exc:
            if is_empty_result_error(exc):
                return FetchOutcome(status=FETCH_EMPTY, records=[])
            last_exc = exc
            if attempt < attempts:
                print(f"🔁 抓取失败，第 {attempt}/{attempts} 次尝试，将重试: {exc}")
                sleep_fn(4)
            else:
                print(f"⚠️  时间范围（{start} ~ {end}）{attempts} 次均失败: {exc}")
    return FetchOutcome(status=FETCH_ERROR, records=[], error=last_exc)


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
    skip_info: dict | None = None,
) -> SpeciesWindow | None:
    """
    Pick a publishable window.

    Default cascade:
    1. Recent window (usually 7 days). If species > min_species, publish it.
    2. Else do not publish the recent list; fetch last 30 days.
       Publish 30 days when species > min_species.
    3. Else union the same calendar month across the past `historical_years` years.
       Publish as "近期可能鸟种" only when that union also has more than min_species.
    4. If a recent window failed with an API error (not a real empty result), skip
       so the frontend keeps the previous folder. Same if historical is empty or
       still ≤ min_species.

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

    def skip(reason: str) -> None:
        if skip_info is not None:
            skip_info["reason"] = reason

    if explicit_range:
        outcome = fetch_records_allow_empty(start=recent_start, end=recent_end, **fetch_kwargs)
        if not outcome.known:
            print(f"❌ {loc_name}: 指定区间（{recent_start} ~ {recent_end}）接口失败，不写入")
            skip(f"指定区间（{recent_start} ~ {recent_end}）接口失败")
            return None
        if not outcome.records:
            print(f"❌ {loc_name}: 指定区间（{recent_start} ~ {recent_end}）无记录")
            skip(f"指定区间（{recent_start} ~ {recent_end}）无记录")
            return None
        write_bird_text(outcome.records, text_file)
        return SpeciesWindow(
            records=outcome.records,
            start=recent_start,
            end=recent_end,
            source=recent_source_for_span(recent_start, recent_end),
        )

    recent_days = (recent_end - recent_start).days + 1
    print(f"🔎 {loc_name}: 先查近 {recent_days} 天（{recent_start} ~ {recent_end}）")
    recent_outcome = fetch_records_allow_empty(start=recent_start, end=recent_end, **fetch_kwargs)
    count_recent = len(recent_outcome.records)
    if recent_outcome.known:
        print(f"📊 {loc_name} 近窗口去重鸟种: {count_recent}")
    else:
        print(f"⚠️  {loc_name} 近窗口接口失败，不当成 0 种: {recent_outcome.error}")
    if recent_outcome.known and is_sufficient(count_recent, min_species):
        write_bird_text(recent_outcome.records, text_file)
        return SpeciesWindow(
            records=recent_outcome.records,
            start=recent_start,
            end=recent_end,
            source=recent_source_for_span(recent_start, recent_end),
        )

    if recent_outcome.known:
        print(
            f"⚠️  {loc_name}: 近窗口 {count_recent} 种 ≤ {min_species}，不写入前端，改查近 {RECENT_MONTH_DAYS} 天"
        )
    else:
        print(f"⚠️  {loc_name}: 近窗口失败，改查近 {RECENT_MONTH_DAYS} 天")
    if recent_days >= RECENT_MONTH_DAYS:
        month_outcome = recent_outcome
        month_start, month_end = recent_start, recent_end
    else:
        month_start, month_end = last_n_days_range(today, RECENT_MONTH_DAYS)
        month_outcome = fetch_records_allow_empty(start=month_start, end=month_end, **fetch_kwargs)
    count_month = len(month_outcome.records)
    if month_outcome.known:
        print(
            f"📊 {loc_name} 近{RECENT_MONTH_DAYS}天去重鸟种: {count_month}（{month_start} ~ {month_end}）"
        )
    else:
        print(
            f"⚠️  {loc_name} 近{RECENT_MONTH_DAYS}天接口失败，不当成 0 种"
            f"（{month_start} ~ {month_end}）: {month_outcome.error}"
        )
    if month_outcome.known and is_sufficient(count_month, min_species):
        write_bird_text(month_outcome.records, text_file)
        return SpeciesWindow(
            records=month_outcome.records,
            start=month_start,
            end=month_end,
            source=SOURCE_RECENT_30D,
            skipped_recent=True,
        )

    if not (
        is_known_insufficient(recent_outcome, min_species)
        and is_known_insufficient(month_outcome, min_species)
    ):
        reason = "近7天或近一月接口失败，未改写前端"
        print(f"❌ {loc_name}: {reason}")
        skip(reason)
        return None

    print(
        f"⚠️  {loc_name}: 近{RECENT_MONTH_DAYS}天 {count_month} 种 ≤ {min_species}，"
        f"改用过去 {historical_years} 年同月并集"
    )
    month_groups = []
    months: list[str] = []
    successful_ranges: list[tuple[date, date]] = []
    for hist_start, hist_end in historical_same_month_ranges(today, historical_years):
        month_key = f"{hist_start.year:04d}-{hist_start.month:02d}"
        hist_outcome = fetch_records_allow_empty(start=hist_start, end=hist_end, **fetch_kwargs)
        if not hist_outcome.known:
            print(f"  📅 {month_key}: 接口失败，跳过该年（{hist_outcome.error}）")
            continue
        recs = hist_outcome.records
        print(f"  📅 {month_key}: {len(recs)} 种")
        if recs:
            month_groups.append(recs)
            months.append(month_key)
            successful_ranges.append((hist_start, hist_end))

    records_hist = union_records(month_groups)
    print(f"📊 {loc_name} {historical_years}年同月并集: {len(records_hist)} 种")
    if not records_hist:
        reason = "近7天与近一月均不足，且历史同月无记录"
        print(f"❌ {loc_name}: 历史同月无记录，跳过写入以保留上次前端数据")
        skip(reason)
        return None
    if not is_sufficient(len(records_hist), min_species):
        reason = (
            f"近7天与近一月均不足，历史同月仍 {len(records_hist)} 种 ≤ {min_species}，未改写前端"
        )
        print(f"❌ {loc_name}: {reason}")
        skip(reason)
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
