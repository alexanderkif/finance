import unittest
from datetime import date
from typing import Literal, cast

from core.metrics import (
    LegQuote,
    OptionLeg,
    Scenario,
    compute_metrics,
    executable_mid,
    format_header,
)
from core.playbook_registry import load_playbooks

EXPIRATION = date(2030, 11, 15)
AS_OF = date(2030, 10, 24)
PLAYBOOKS = load_playbooks()


def leg(
    *,
    side: Literal["buy", "sell"],
    option_type: Literal["call", "put"],
    strike: float,
    bid: float | None,
    ask: float | None,
    delta: float | None = None,
    theta: float | None = None,
    iv: float | None = 0.15,
    open_interest: float | None = 1_000,
    volume: float | None = 500,
    symbol: str = "SPY",
) -> LegQuote:
    return LegQuote(
        symbol=symbol,
        side=side,
        option_type=option_type,
        strike=strike,
        expiration=EXPIRATION,
        bid=bid,
        ask=ask,
        iv=iv,
        delta=delta,
        theta=theta,
        open_interest=open_interest,
        volume=volume,
    )


class MetricsTests(unittest.TestCase):
    def test_bull_put_credit_spread(self) -> None:
        legs = [
            leg(
                side="sell",
                option_type="put",
                strike=732,
                bid=3.00,
                ask=3.20,
                delta=-0.30,
                theta=-0.10,
                open_interest=1_000,
                volume=500,
            ),
            leg(
                side="buy",
                option_type="put",
                strike=729,
                bid=1.50,
                ask=1.70,
                delta=-0.18,
                theta=-0.05,
                open_interest=800,
                volume=400,
            ),
        ]

        metrics = compute_metrics(
            legs=legs,
            playbook=PLAYBOOKS["bull_put_spread"],
            underlying_price=770.0,
            as_of=AS_OF,
            atm_iv=0.14,
        )

        self.assertEqual(metrics.net_credit_debit, 150.0)
        self.assertEqual(metrics.max_profit, 150.0)
        self.assertEqual(metrics.max_loss, 150.0)
        self.assertEqual(metrics.breakeven, 730.5)
        self.assertEqual(metrics.probability_positive, 0.7)
        self.assertEqual(metrics.theta_daily, 5.0)
        self.assertIsNone(metrics.iv_rank)
        self.assertIn("iv_rank_unavailable", metrics.warnings)
        self.assertEqual(metrics.event_flags, ["earnings", "dividends", "macro"])
        self.assertEqual(metrics.liquidity.bid_ask_spread_pct, 12.5)
        self.assertEqual(metrics.liquidity.open_interest, 800)
        self.assertEqual(metrics.liquidity.volume, 400)
        self.assertEqual(metrics.liquidity.rating, "fair")
        scenario = cast(Scenario, metrics.scenario_1sigma)
        self.assertEqual(scenario.days_to_expiration, 22)
        self.assertEqual(scenario.expected_move, 26.47)
        self.assertEqual(scenario.low, 743.53)
        self.assertEqual(scenario.high, 796.47)

    def test_bull_call_debit_spread(self) -> None:
        legs = [
            leg(
                side="buy",
                option_type="call",
                strike=729,
                bid=3.90,
                ask=4.10,
                delta=0.55,
                theta=-0.08,
            ),
            leg(
                side="sell",
                option_type="call",
                strike=732,
                bid=2.40,
                ask=2.60,
                delta=0.42,
                theta=-0.06,
            ),
        ]

        metrics = compute_metrics(
            legs=legs,
            playbook=PLAYBOOKS["bull_call_spread"],
            underlying_price=730.0,
            as_of=AS_OF,
            atm_iv=0.14,
        )

        self.assertEqual(metrics.net_credit_debit, -150.0)
        self.assertEqual(metrics.max_profit, 150.0)
        self.assertEqual(metrics.max_loss, 150.0)
        self.assertEqual(metrics.breakeven, 730.5)
        self.assertEqual(metrics.probability_positive, 0.55)

    def test_long_call_has_unbounded_profit(self) -> None:
        metrics = compute_metrics(
            legs=[
                leg(
                    side="buy",
                    option_type="call",
                    strike=600,
                    bid=4.90,
                    ask=5.10,
                    delta=0.4,
                    theta=-0.05,
                )
            ],
            playbook=PLAYBOOKS["long_call"],
            underlying_price=610.0,
            as_of=AS_OF,
            atm_iv=0.18,
        )

        self.assertIsNone(metrics.max_profit)
        self.assertEqual(metrics.max_loss, 500.0)
        self.assertEqual(metrics.breakeven, 605.0)
        self.assertEqual(metrics.probability_positive, 0.4)
        self.assertEqual(metrics.net_credit_debit, -500.0)

    def test_short_put_has_bounded_loss(self) -> None:
        metrics = compute_metrics(
            legs=[
                leg(
                    side="sell",
                    option_type="put",
                    strike=700,
                    bid=5.90,
                    ask=6.10,
                    delta=-0.25,
                    theta=-0.04,
                )
            ],
            playbook=PLAYBOOKS["short_put"],
            underlying_price=720.0,
            as_of=AS_OF,
            atm_iv=0.16,
        )

        self.assertEqual(metrics.max_profit, 600.0)
        self.assertEqual(metrics.max_loss, 69_400.0)
        self.assertEqual(metrics.breakeven, 694.0)
        self.assertEqual(metrics.probability_positive, 0.75)

    def test_short_call_has_unbounded_loss(self) -> None:
        metrics = compute_metrics(
            legs=[
                leg(
                    side="sell",
                    option_type="call",
                    strike=800,
                    bid=2.90,
                    ask=3.10,
                    delta=0.2,
                    theta=-0.03,
                )
            ],
            playbook=PLAYBOOKS["short_call"],
            underlying_price=770.0,
            as_of=AS_OF,
            atm_iv=0.14,
        )

        self.assertEqual(metrics.max_profit, 300.0)
        self.assertIsNone(metrics.max_loss)
        self.assertEqual(metrics.breakeven, 803.0)

    def test_missing_delta_removes_probability(self) -> None:
        metrics = compute_metrics(
            legs=[
                leg(
                    side="buy",
                    option_type="call",
                    strike=600,
                    bid=4.90,
                    ask=5.10,
                    delta=None,
                    theta=-0.05,
                )
            ],
            playbook=PLAYBOOKS["long_call"],
            underlying_price=610.0,
            as_of=AS_OF,
            atm_iv=None,
        )

        self.assertIsNone(metrics.probability_positive)
        self.assertIn("delta_unavailable", metrics.warnings)
        self.assertIsNone(metrics.scenario_1sigma)
        self.assertIn("scenario_1sigma_unavailable", metrics.warnings)

    def test_non_executable_quote_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            executable_mid(
                leg(
                    side="buy",
                    option_type="call",
                    strike=600,
                    bid=0.0,
                    ask=5.10,
                )
            )

    def test_headers_are_deterministic(self) -> None:
        spread = [
            OptionLeg(
                symbol="XSP",
                side="sell",
                option_type="put",
                strike=732,
                expiration=EXPIRATION,
            ),
            OptionLeg(
                symbol="XSP",
                side="buy",
                option_type="put",
                strike=729,
                expiration=EXPIRATION,
            ),
        ]
        single = OptionLeg(
            symbol="SPY",
            side="buy",
            option_type="call",
            strike=600,
            expiration=EXPIRATION,
        )

        self.assertEqual(
            format_header("Bull Put Spread", spread),
            "Bull Put Spread XSP 732/729 2030-11-15",
        )
        self.assertEqual(
            format_header("Long Call", [single]),
            "Long Call SPY 600 2030-11-15",
        )


if __name__ == "__main__":
    unittest.main()
