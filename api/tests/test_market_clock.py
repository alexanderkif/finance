import unittest
from datetime import UTC, datetime

from core.market_clock import market_session, quote_age_minutes


class MarketSessionTests(unittest.TestCase):
    def test_pre_market_points_to_the_same_day_open(self) -> None:
        session = market_session(datetime(2026, 11, 10, 12, 20, tzinfo=UTC))

        self.assertEqual(session.status, "pre_market")
        self.assertFalse(session.is_open)
        self.assertEqual(
            session.next_open,
            datetime(2026, 11, 10, 14, 30, tzinfo=UTC),
        )
        self.assertEqual(
            session.next_close,
            datetime(2026, 11, 10, 21, 0, tzinfo=UTC),
        )

    def test_regular_session_is_open(self) -> None:
        session = market_session(datetime(2026, 11, 10, 15, 0, tzinfo=UTC))

        self.assertEqual(session.status, "open")
        self.assertTrue(session.is_open)
        self.assertEqual(
            session.next_close,
            datetime(2026, 11, 10, 21, 0, tzinfo=UTC),
        )
        self.assertEqual(
            session.next_open,
            datetime(2026, 11, 11, 14, 30, tzinfo=UTC),
        )

    def test_after_hours_uses_the_next_session(self) -> None:
        session = market_session(datetime(2026, 11, 10, 22, 0, tzinfo=UTC))

        self.assertEqual(session.status, "after_hours")
        self.assertFalse(session.is_open)
        self.assertEqual(
            session.next_open,
            datetime(2026, 11, 11, 14, 30, tzinfo=UTC),
        )
        self.assertEqual(
            session.next_close,
            datetime(2026, 11, 11, 21, 0, tzinfo=UTC),
        )

    def test_overnight_is_closed_and_points_to_today(self) -> None:
        session = market_session(datetime(2026, 11, 10, 6, 0, tzinfo=UTC))

        self.assertEqual(session.status, "closed")
        self.assertFalse(session.is_open)
        self.assertEqual(
            session.next_open,
            datetime(2026, 11, 10, 14, 30, tzinfo=UTC),
        )

    def test_weekend_points_to_monday(self) -> None:
        session = market_session(datetime(2026, 11, 14, 15, 0, tzinfo=UTC))

        self.assertEqual(session.status, "closed")
        self.assertFalse(session.is_open)
        self.assertEqual(
            session.next_open,
            datetime(2026, 11, 16, 14, 30, tzinfo=UTC),
        )
        self.assertEqual(
            session.next_close,
            datetime(2026, 11, 16, 21, 0, tzinfo=UTC),
        )

    def test_daylight_saving_shift_is_applied(self) -> None:
        session = market_session(datetime(2026, 7, 15, 12, 0, tzinfo=UTC))

        self.assertEqual(session.status, "pre_market")
        self.assertEqual(
            session.next_open,
            datetime(2026, 7, 15, 13, 30, tzinfo=UTC),
        )

    def test_quote_age_is_reported_in_minutes(self) -> None:
        as_of = datetime(2026, 11, 10, 12, 20, 26, tzinfo=UTC)
        now = datetime(2026, 11, 10, 12, 51, 0, tzinfo=UTC)

        self.assertEqual(quote_age_minutes(as_of, now), 30)


if __name__ == "__main__":
    unittest.main()
