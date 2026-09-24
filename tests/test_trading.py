import sys
import unittest
from decimal import ROUND_UP
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading import (
    PositionLookupError,
    build_protection_prices,
    get_position_snapshot,
    has_expected_protection_orders,
    normalize_order_quantity,
    normalize_trigger_price,
    passes_min_notional,
    quantize_quantity,
    reconcile_symbol_protection,
    trade_symbol,
)


class TradingHelpersTest(unittest.TestCase):
    def setUp(self):
        self.symbol_info = {
            "symbol": "BTCUSDT",
            "filters": [
                {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "1000", "stepSize": "0.001"},
                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "maxQty": "1000", "stepSize": "0.001"},
                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                {"filterType": "PRICE_FILTER", "minPrice": "0.1", "maxPrice": "1000000", "tickSize": "0.1"},
            ],
        }

    def test_quantize_quantity_rounds_down_to_step(self):
        self.assertEqual(str(quantize_quantity(0.0019, "0.001")), "0.001")

    def test_normalize_order_quantity_returns_zero_below_min(self):
        self.assertEqual(str(normalize_order_quantity(self.symbol_info, 0.0008)), "0")

    def test_min_notional_check(self):
        quantity = normalize_order_quantity(self.symbol_info, 0.002)
        self.assertTrue(passes_min_notional(self.symbol_info, quantity, 40000))
        self.assertFalse(passes_min_notional(self.symbol_info, quantity, 1000))

    def test_normalize_trigger_price_honors_tick_size(self):
        self.assertEqual(str(normalize_trigger_price(self.symbol_info, 100.19)), "100.1")
        self.assertEqual(str(normalize_trigger_price(self.symbol_info, 100.11, rounding=ROUND_UP)), "100.2")

    def test_build_protection_prices_for_long_position(self):
        prices = build_protection_prices(self.symbol_info, 0.01, 100.0)
        self.assertEqual(str(prices["stop_loss"]), "99.0")
        self.assertEqual(str(prices["take_profit"]), "102.0")

    def test_build_protection_prices_for_short_position(self):
        prices = build_protection_prices(self.symbol_info, -0.01, 100.0)
        self.assertEqual(str(prices["stop_loss"]), "101.0")
        self.assertEqual(str(prices["take_profit"]), "98.0")

    def test_has_expected_protection_orders(self):
        open_orders = [
            {"orderType": "STOP_MARKET", "side": "SELL", "closePosition": True},
            {"orderType": "TAKE_PROFIT_MARKET", "side": "SELL", "closePosition": True},
        ]
        self.assertTrue(has_expected_protection_orders(open_orders, "SELL"))
        self.assertFalse(has_expected_protection_orders(open_orders, "BUY"))


class PositionLookupSafetyTest(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.client.futures_get_position_mode.return_value = {"dualSidePosition": False}
        self.client.futures_get_open_algo_orders.return_value = [
            {
                "symbol": "BTCUSDT",
                "algoId": 101,
                "orderType": "STOP_MARKET",
                "side": "SELL",
                "closePosition": True,
            },
            {
                "symbol": "BTCUSDT",
                "algoId": 102,
                "orderType": "TAKE_PROFIT_MARKET",
                "side": "SELL",
                "closePosition": True,
            },
        ]

    def assert_orders_untouched(self):
        self.client.futures_cancel_algo_order.assert_not_called()
        self.client.futures_cancel_order.assert_not_called()
        self.client.futures_create_algo_order.assert_not_called()
        self.client.futures_create_order.assert_not_called()
        self.client.futures_change_leverage.assert_not_called()

    def test_position_lookup_failure_preserves_protection_during_reconciliation(self):
        self.client.futures_position_information.side_effect = TimeoutError("Lookup failed")
        with patch("trading.DRY_RUN", False), patch(
            "trading.get_symbol_info", return_value={"symbol": "BTCUSDT"}
        ):
            with self.assertRaises(PositionLookupError):
                reconcile_symbol_protection(self.client, "BTCUSDT", fallback_price=100.0)
        self.assert_orders_untouched()

    def test_exchange_api_error_cannot_cancel_protection_or_open_a_trade(self):
        from binance.exceptions import BinanceAPIException

        self.client.futures_position_information.side_effect = BinanceAPIException(
            None, 503, '{"code": -1001, "msg": "Disconnected"}'
        )
        with patch("trading.DRY_RUN", False), patch(
            "trading.get_symbol_info", return_value={"symbol": "BTCUSDT"}
        ), patch("trading.get_klines", return_value=list(range(1, 101))):
            with self.assertRaises(PositionLookupError):
                trade_symbol(self.client, "BTCUSDT")
        self.assert_orders_untouched()

    def test_missing_or_invalid_position_records_are_unknown(self):
        responses = [
            [],
            [{"symbol": "ETHUSDT", "positionAmt": "0"}],
            [{"symbol": "BTCUSDT"}],
            [{"symbol": "BTCUSDT", "positionAmt": ""}],
            [{"symbol": "BTCUSDT", "positionAmt": "nan"}],
            [{"symbol": "BTCUSDT", "positionAmt": "inf"}],
        ]
        for response in responses:
            with self.subTest(response=response):
                self.client.futures_position_information.return_value = response
                with self.assertRaises(PositionLookupError):
                    get_position_snapshot(self.client, "BTCUSDT")
        self.assert_orders_untouched()

    def test_confirmed_flat_position_can_still_clean_up_orphan_orders(self):
        self.client.futures_position_information.return_value = [
            {"symbol": "BTCUSDT", "positionAmt": "0", "entryPrice": "0"}
        ]
        with patch("trading.DRY_RUN", False), patch(
            "trading.get_symbol_info", return_value={"symbol": "BTCUSDT"}
        ):
            self.assertFalse(
                reconcile_symbol_protection(self.client, "BTCUSDT", fallback_price=100.0)
            )
        self.assertEqual(
            [call.kwargs["algoId"] for call in self.client.futures_cancel_algo_order.call_args_list],
            [101, 102],
        )
        self.client.futures_create_order.assert_not_called()

    def test_confirmed_open_position_keeps_matching_protective_orders(self):
        self.client.futures_position_information.return_value = [
            {"symbol": "BTCUSDT", "positionAmt": "0.01", "entryPrice": "100"}
        ]
        with patch("trading.DRY_RUN", False), patch(
            "trading.get_symbol_info", return_value={"symbol": "BTCUSDT"}
        ):
            self.assertTrue(
                reconcile_symbol_protection(self.client, "BTCUSDT", fallback_price=100.0)
            )
        self.assert_orders_untouched()


if __name__ == "__main__":
    unittest.main()
