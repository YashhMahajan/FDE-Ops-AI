from datetime import UTC, datetime, timedelta

import pytest

from fdeops.core.clock import FakeClock, SystemClock


def test_fake_clock_sleep_advances() -> None:
    start = datetime(2026, 9, 15, tzinfo=UTC)
    clock = FakeClock(start)
    clock.sleep(1.5)
    assert clock.now() == start + timedelta(seconds=1.5)
    clock.advance(10)
    assert clock.now() == start + timedelta(seconds=11.5)


def test_fake_clock_requires_aware_datetime() -> None:
    with pytest.raises(ValueError):
        FakeClock(datetime(2026, 1, 1))


def test_system_clock_is_utc() -> None:
    assert SystemClock().now().tzinfo is not None
