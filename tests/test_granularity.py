"""Tests for detecting whether an existing statistics series is hourly or daily."""
from datetime import datetime, timedelta, timezone

from custom_components.southern_company.coordinator import series_is_hourly

T0 = datetime(2026, 9, 1, 5, tzinfo=timezone.utc)


def rows(step: timedelta, n: int, as_timestamp: bool = True) -> list[dict]:
    starts = [T0 + step * i for i in range(n)]
    return [{"start": s.timestamp() if as_timestamp else s, "sum": float(i)} for i, s in enumerate(starts)]


def test_daily_series_is_not_hourly():
    # statistics_during_period(..., "hour") still returns one row per day for a daily series;
    # that used to be mistaken for an hourly series and stopped all further updates.
    assert series_is_hourly(rows(timedelta(days=1), 30)) is False


def test_hourly_series_is_hourly():
    assert series_is_hourly(rows(timedelta(hours=1), 48)) is True


def test_hourly_series_with_gaps_is_still_hourly():
    data = rows(timedelta(hours=1), 10) + [
        {"start": (T0 + timedelta(days=3, hours=h)).timestamp(), "sum": 99.0} for h in range(5)
    ]
    assert series_is_hourly(data) is True


def test_datetime_starts_are_accepted():
    assert series_is_hourly(rows(timedelta(hours=1), 5, as_timestamp=False)) is True
    assert series_is_hourly(rows(timedelta(days=1), 5, as_timestamp=False)) is False


def test_too_few_rows_defaults_to_daily():
    assert series_is_hourly([]) is False
    assert series_is_hourly(rows(timedelta(hours=1), 1)) is False
