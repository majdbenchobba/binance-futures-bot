import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reporting import (
    build_alert_context,
    build_position_signature,
    count_protection_orders_by_symbol,
    empty_position_signature,
    extract_open_positions,
    format_cycle_summary,
    format_position_lines,
    increment_cycle_count,
    remember_position_signature,
    should_alert_on_position_change,
    should_log_cycle_report,
)
from risk_controls import default_state


class ReportingTest(unittest.TestCase):
    def test_count_protection_orders_by_symbol_counts_only_protection_orders(self):
        orders = [
            {"symbol": "ETHUSDT", "orderType": "STOP_MARKET", "closePosition": True},
            {"symbol": "ETHUSDT", "orderType": "TAKE_PROFIT_MARKET", "closePosition": True},
            {"symbol": "BTCUSDT", "orderType": "STOP_MARKET", "closePosition": True},
            {"symbol": "XRPUSDT", "orderType": "LIMIT", "closePosition": False},
        ]

        counts = count_protection_orders_by_symbol(orders)
        self.assertEqual(counts, {"ETHUSDT": 2, "BTCUSDT": 1})

    def test_extract_open_positions_and_signature_are_order_stable(self):
        counts = {"ETHUSDT": 2, "BTCUSDT": 1}
        positions_a = extract_open_positions(
            [
                {
                    "symbol": "ETHUSDT",
                    "positionAmt": "-0.011",
                    "entryPrice": "2100.1",
                    "markPrice": "2095.5",
                    "unRealizedProfit": "0.0500",
                    "notional": "-23.05",
                    "liquidationPrice": "2500.0",
                    "leverage": "5",
                },
                {
                    "symbol": "BTCUSDT",
                    "positionAmt": "0.001",
                    "entryPrice": "70000",
                    "markPrice": "70100",
                    "unRealizedProfit": "0.1",
                    "notional": "70.1",
                    "liquidationPrice": "50000",
                    "leverage": "3",
                },
            ],
            protection_counts=counts,
        )
        positions_b = list(reversed(positions_a))

        signature_a = build_position_signature(
            {"positions": positions_a, "protection_counts": counts}
        )
        signature_b = build_position_signature(
            {"positions": positions_b, "protection_counts": counts}
        )

        self.assertEqual(signature_a, signature_b)

    def test_cycle_reporting_and_position_change_tracking(self):
        state = default_state()
        cycle_count = increment_cycle_count(state)
        self.assertEqual(cycle_count, 1)
        self.assertTrue(should_log_cycle_report(state, state_changed=False, report_every_cycles=1))
        self.assertFalse(should_log_cycle_report(state, state_changed=False, report_every_cycles=2))

        self.assertTrue(should_alert_on_position_change(state, "abc"))
        remember_position_signature(state, "abc")
        self.assertFalse(should_alert_on_position_change(state, "abc"))
        self.assertTrue(should_alert_on_position_change(state, "def"))
        blank_state = default_state()
        self.assertFalse(should_alert_on_position_change(blank_state, empty_position_signature()))

    def test_formatters_include_balance_and_positions(self):
        snapshot = {
            "balance": {"wallet_balance": 5000.0, "available_balance": 4990.0},
            "total_unrealized_pnl": 12.5,
            "open_position_count": 1,
            "protection_order_count": 2,
            "positions": [
                {
                    "symbol": "ETHUSDT",
                    "side": "LONG",
                    "quantity": 0.011,
                    "entry_price": 2100.0,
                    "mark_price": 2110.0,
                    "unrealized_pnl": 0.11,
                    "leverage": 5,
                    "protection_count": 2,
                    "liquidation_price": 1500.0,
                }
            ],
        }

        summary = format_cycle_summary(snapshot, 3)
        lines = format_position_lines(snapshot)
        context = build_alert_context(snapshot, 3)

        self.assertIn("Cycle 3", summary)
        self.assertIn("wallet=5000.00", summary)
        self.assertEqual(len(lines), 1)
        self.assertIn("ETHUSDT LONG", lines[0])
        self.assertEqual(context["cycle_count"], 3)
        self.assertEqual(context["positions"][0]["symbol"], "ETHUSDT")


if __name__ == "__main__":
    unittest.main()
