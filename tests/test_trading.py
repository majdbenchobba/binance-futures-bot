import sys
import unittest
from decimal import ROUND_UP
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading import (
    build_protection_prices,
    has_expected_protection_orders,
    normalize_order_quantity,
    normalize_trigger_price,
    passes_min_notional,
    quantize_quantity,
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


if __name__ == "__main__":
    unittest.main()
