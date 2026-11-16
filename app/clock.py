from __future__ import annotations

from datetime import datetime, timezone


class Clock:
    """Injectable clock interface.

    Production: returns current UTC time.
    Tests: use a fake clock that returns deterministic times.
    """

    def now(self) -> datetime:
        raise NotImplementedError


class RealClock(Clock):
    """Production clock that returns current UTC time."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock(Clock):
    """Fixed clock that returns a deterministic time.

    Useful for tests where time must not advance unexpectedly.
    """

    def __init__(self, fixed_time: datetime) -> None:
        self._fixed_time = fixed_time

    def now(self) -> datetime:
        return self._fixed_time