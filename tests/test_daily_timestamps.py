"""Daily rows are stamped at local midnight, and old UTC-midnight rows are rebuilt (issue #146)."""

from datetime import datetime, timedelta
from types import SimpleNamespace

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.southern_company.coordinator import SouthernCompanyCoordinator

USAGE_ID = "southern_company:energy_usage_123"
COST_ID = "southern_company:energy_cost_123"


async def _value(value):
    return value


class FakeAccount:
    number = "123"
    name = "House"
    service_point_number = "1"

    def __init__(self, days):
        self.days = days

    async def get_hourly_data(self, start, end, jwt):
        raise RuntimeError("daily-only account")

    async def get_daily_data(self, start, end, jwt):
        return self.days


class FakeApi:
    def __init__(self, account):
        self.account = account

    @property
    def jwt(self):
        return _value("jwt")

    @property
    def accounts(self):
        return _value([self.account])


def _days(n=10):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    # Naive labels, as southern_company_api returns them.
    return [
        SimpleNamespace(date=today - timedelta(days=n - i), usage=10.0 + i, cost=1.0)
        for i in range(n)
    ]


async def _run(hass, coordinator):
    await coordinator._insert_statistics()
    await async_wait_recording_done(hass)


async def _rows(hass, statistic_id):
    start = dt_util.utcnow() - timedelta(days=60)
    stats = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        start,
        None,
        {statistic_id},
        "hour",
        None,
        {"sum", "state"},
    )
    return stats.get(statistic_id, [])


def _local_hours(rows):
    return {dt_util.as_local(dt_util.utc_from_timestamp(r["start"])).hour for r in rows}


async def test_first_import_is_at_local_midnight(hass):
    await hass.config.async_set_time_zone("America/Chicago")
    days = _days()
    await _run(hass, SouthernCompanyCoordinator(hass, FakeApi(FakeAccount(days))))

    rows = await _rows(hass, USAGE_ID)
    assert len(rows) == len(days)
    assert _local_hours(rows) == {0}


async def test_utc_midnight_history_is_rebuilt_without_double_counting(hass):
    days = _days()
    coordinator = SouthernCompanyCoordinator(hass, FakeApi(FakeAccount(days)))

    # Rows written while the zone is UTC sit at 00:00 UTC, like earlier versions wrote them.
    await hass.config.async_set_time_zone("UTC")
    await _run(hass, coordinator)
    await hass.config.async_set_time_zone("America/Chicago")
    assert _local_hours(await _rows(hass, USAGE_ID)) == {19}

    await _run(hass, coordinator)

    rows = await _rows(hass, USAGE_ID)
    assert len(rows) == len(days)
    assert _local_hours(rows) == {0}
    assert rows[-1]["sum"] == sum(d.usage for d in days)
    assert len(await _rows(hass, COST_ID)) == len(days)

    # A later update leaves an aligned series alone.
    await _run(hass, coordinator)
    assert await _rows(hass, USAGE_ID) == rows
