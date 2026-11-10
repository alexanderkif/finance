from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

EXCHANGE_TIMEZONE = "America/New_York"
_EASTERN = ZoneInfo(EXCHANGE_TIMEZONE)
_PRE_MARKET_OPEN = time(4, 0)
_REGULAR_OPEN = time(9, 30)
_REGULAR_CLOSE = time(16, 0)
_AFTER_HOURS_CLOSE = time(20, 0)

MarketStatus = Literal["pre_market", "open", "after_hours", "closed"]


@dataclass(frozen=True)
class MarketSession:
    status: MarketStatus
    is_open: bool
    exchange_time: datetime
    next_open: datetime
    next_close: datetime
    timezone: str = EXCHANGE_TIMEZONE

    def to_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "is_open": self.is_open,
            "exchange_time": self.exchange_time.astimezone(UTC).isoformat(),
            "next_open": self.next_open.astimezone(UTC).isoformat(),
            "next_close": self.next_close.astimezone(UTC).isoformat(),
            "timezone": self.timezone,
        }


def market_session(now: datetime | None = None) -> MarketSession:
    reference = (now or datetime.now(UTC)).astimezone(UTC)
    local = reference.astimezone(_EASTERN)
    today = local.date()
    today_open, today_close = _session_bounds(today)

    if _is_weekday(today) and today_open <= local < today_close:
        status: MarketStatus = "open"
        next_open_day = _next_weekday(today + timedelta(days=1))
        next_open, _ = _session_bounds(next_open_day)
        next_close = today_close
    elif _is_weekday(today) and _PRE_MARKET_OPEN <= local.time() < _REGULAR_OPEN:
        status = "pre_market"
        next_open = today_open
        next_close = today_close
    elif _is_weekday(today) and _REGULAR_CLOSE <= local.time() < _AFTER_HOURS_CLOSE:
        status = "after_hours"
        next_open_day = _next_weekday(today + timedelta(days=1))
        next_open, next_close = _session_bounds(next_open_day)
    elif _is_weekday(today) and local < today_open:
        status = "closed"
        next_open = today_open
        next_close = today_close
    else:
        status = "closed"
        next_open_day = _next_weekday(today + timedelta(days=1))
        next_open, next_close = _session_bounds(next_open_day)

    return MarketSession(
        status=status,
        is_open=status == "open",
        exchange_time=local,
        next_open=next_open,
        next_close=next_close,
    )


def quote_age_minutes(as_of: datetime, now: datetime | None = None) -> int | None:
    value = as_of if as_of.tzinfo is not None else as_of.replace(tzinfo=UTC)
    reference = now or datetime.now(UTC)
    seconds = (reference.astimezone(UTC) - value.astimezone(UTC)).total_seconds()
    return max(0, int(seconds // 60))


def _session_bounds(day: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(day, _REGULAR_OPEN, tzinfo=_EASTERN),
        datetime.combine(day, _REGULAR_CLOSE, tzinfo=_EASTERN),
    )


def _is_weekday(day: date) -> bool:
    return day.weekday() < 5


def _next_weekday(day: date) -> date:
    candidate = day
    while not _is_weekday(candidate):
        candidate += timedelta(days=1)
    return candidate
