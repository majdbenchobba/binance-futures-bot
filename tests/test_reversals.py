import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from binance.exceptions import BinanceAPIException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import trading


def exchange_error():
    return BinanceAPIException(None, 503, '{"code": -1001, "msg": "Synthetic exchange error"}')


class ReversalSafetyTest(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.short = [{"symbol": "BTCUSDT", "positionAmt": "-1", "entryPrice": "100"}]
        self.flat = [{"symbol": "BTCUSDT", "positionAmt": "0", "entryPrice": "0"}]
        self.protection = [
            {"algoId": 101, "orderType": "STOP_MARKET", "side": "BUY", "closePosition": True},
            {"algoId": 102, "orderType": "TAKE_PROFIT_MARKET", "side": "BUY", "closePosition": True},
        ]
        self.symbol_info = {
            "symbol": "BTCUSDT",
            "filters": [
                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "maxQty": "1000", "stepSize": "0.001"},
                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                {"filterType": "PRICE_FILTER", "minPrice": "0.1", "maxPrice": "1000000", "tickSize": "0.1"},
            ],
        }
        self.client.futures_get_position_mode.return_value = {"dualSidePosition": False}
        self.client.futures_position_information.side_effect = [self.short, self.flat]
        self.client.futures_get_open_algo_orders.side_effect = [self.protection, []]
        self.client.futures_create_order.side_effect = [
            {"status": "FILLED", "avgPrice": "100", "executedQty": "1"},
            {"status": "FILLED", "avgPrice": "100", "executedQty": "0.1"},
        ]
        self.client.futures_account_balance.return_value = [
            {"asset": "USDT", "availableBalance": "1000", "balance": "1000"}
        ]
        self.client.futures_create_algo_order.return_value = {"algoId": 200}
        for name, value in {
            "DRY_RUN": False, "TRADE_BALANCE_FRACTION": 0.01, "SMA_SHORT": 7,
            "SMA_LONG": 25, "STOP_LOSS_PCT": 0.01, "TAKE_PROFIT_PCT": 0.02,
        }.items():
            self.enterContext(patch.object(trading, name, value))
        self.enterContext(patch.object(trading, "get_symbol_info", return_value=self.symbol_info))
        self.enterContext(patch.object(trading, "get_klines", return_value=list(range(1, 101))))

    def assert_no_new_entry(self):
        self.assertTrue(
            all(call.kwargs.get("reduceOnly") == "true"
                for call in self.client.futures_create_order.call_args_list)
        )
        self.client.futures_create_algo_order.assert_not_called()
        self.client.futures_change_leverage.assert_not_called()

    def assert_protection_retained(self):
        self.client.futures_cancel_algo_order.assert_not_called()
        self.client.futures_cancel_order.assert_not_called()

    def test_failed_close_preserves_protection_and_prevents_reentry(self):
        self.client.futures_create_order.side_effect = exchange_error()
        self.assertFalse(trading.trade_symbol(self.client, "BTCUSDT"))
        self.assertEqual(self.client.futures_create_order.call_count, 1)
        self.assert_no_new_entry()
        self.assert_protection_retained()

    def test_close_timeout_is_not_retried_or_followed_by_an_entry(self):
        self.client.futures_create_order.side_effect = TimeoutError("Synthetic timeout")
        self.assertFalse(trading.trade_symbol(self.client, "BTCUSDT"))
        self.assertEqual(self.client.futures_create_order.call_count, 1)
        self.assert_no_new_entry()
        self.assert_protection_retained()

    def test_pending_partial_and_missing_close_acknowledgements_defer_reentry(self):
        for status in ("NEW", "PARTIALLY_FILLED", "EXPIRED", ""):
            with self.subTest(status=status):
                self.client.futures_position_information.side_effect = [self.short, self.flat]
                self.client.futures_create_order.side_effect = None
                self.client.futures_create_order.return_value = {"status": status}
                self.assertFalse(trading.trade_symbol(self.client, "BTCUSDT"))
                self.assert_no_new_entry()
                self.assert_protection_retained()

    def test_filled_close_with_remaining_position_retains_protection(self):
        remaining = [{"symbol": "BTCUSDT", "positionAmt": "-0.4", "entryPrice": "100"}]
        self.client.futures_position_information.side_effect = [self.short, remaining]
        self.assertFalse(trading.trade_symbol(self.client, "BTCUSDT"))
        self.assert_no_new_entry()
        self.assert_protection_retained()

    def test_position_read_failure_after_close_retains_protection(self):
        self.client.futures_position_information.side_effect = [self.short, TimeoutError("Unknown state")]
        self.assertFalse(trading.trade_symbol(self.client, "BTCUSDT"))
        self.assert_no_new_entry()
        self.assert_protection_retained()

    def test_uncloseable_quantity_never_removes_protection(self):
        self.client.futures_position_information.side_effect = [
            [{"symbol": "BTCUSDT", "positionAmt": "-0.0001", "entryPrice": "100"}]
        ]
        self.assertFalse(trading.trade_symbol(self.client, "BTCUSDT"))
        self.client.futures_create_order.assert_not_called()
        self.assert_no_new_entry()
        self.assert_protection_retained()

    def test_cancellation_failure_after_confirmed_close_prevents_entry(self):
        self.client.futures_cancel_algo_order.side_effect = exchange_error()
        self.assertFalse(trading.trade_symbol(self.client, "BTCUSDT"))
        self.assert_no_new_entry()

    def test_orders_still_visible_after_cancellation_prevent_entry(self):
        self.client.futures_get_open_algo_orders.side_effect = [self.protection, self.protection[:1]]
        self.assertFalse(trading.trade_symbol(self.client, "BTCUSDT"))
        self.assert_no_new_entry()

    def test_unknown_or_malformed_order_list_prevents_entry(self):
        for response in (exchange_error(), {"unexpected": "response"}):
            with self.subTest(response=response):
                self.client.futures_position_information.side_effect = [self.flat]
                self.client.futures_get_open_algo_orders.side_effect = [response]
                self.assertFalse(trading.trade_symbol(self.client, "BTCUSDT"))
                self.client.futures_create_order.assert_not_called()
                self.assert_protection_retained()

    def test_confirmed_flat_state_and_order_cleanup_allow_reentry(self):
        self.assertTrue(trading.trade_symbol(self.client, "BTCUSDT"))
        orders = self.client.futures_create_order.call_args_list
        self.assertEqual(len(orders), 2)
        self.assertEqual(orders[0].kwargs["reduceOnly"], "true")
        self.assertNotIn("reduceOnly", orders[1].kwargs)
        self.assertEqual(self.client.futures_position_information.call_count, 2)
        self.assertEqual(self.client.futures_cancel_algo_order.call_count, 2)
        self.assertEqual(
            [call.kwargs["side"] for call in self.client.futures_create_algo_order.call_args_list],
            ["SELL", "SELL"],
        )
        calls = [call[0] for call in self.client.mock_calls]
        second_position_read = [
            index for index, name in enumerate(calls) if name == "futures_position_information"
        ][1]
        self.assertGreater(calls.index("futures_cancel_algo_order"), second_position_read)

    def test_manage_only_close_uses_confirmation_without_reentry(self):
        self.assertFalse(trading.trade_symbol(self.client, "BTCUSDT", allow_new_entries=False))
        self.assertEqual(self.client.futures_position_information.call_count, 2)
        self.assertEqual(self.client.futures_cancel_algo_order.call_count, 2)
        self.assertEqual(self.client.futures_create_order.call_count, 1)
        self.assert_no_new_entry()

    def test_manage_only_failed_close_keeps_existing_protection(self):
        self.client.futures_create_order.side_effect = exchange_error()
        self.assertFalse(trading.trade_symbol(self.client, "BTCUSDT", allow_new_entries=False))
        self.assert_no_new_entry()
        self.assert_protection_retained()

    def test_leverage_rejection_prevents_a_new_entry(self):
        self.client.futures_change_leverage.side_effect = exchange_error()
        self.assertFalse(trading.trade_symbol(self.client, "BTCUSDT"))
        self.assertEqual(self.client.futures_create_order.call_count, 1)
        self.client.futures_create_algo_order.assert_not_called()

    def test_dry_run_sends_no_order_cancellation_or_leverage_mutations(self):
        with patch.object(trading, "DRY_RUN", True):
            self.assertFalse(trading.trade_symbol(self.client, "BTCUSDT"))
        self.client.futures_create_order.assert_not_called()
        self.assert_no_new_entry()
        self.assert_protection_retained()


if __name__ == "__main__":
    unittest.main()
