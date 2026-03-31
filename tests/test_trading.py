import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading import normalize_order_quantity, passes_min_notional, quantize_quantity


class TradingHelpersTest(unittest.TestCase):
    def setUp(self):
        self.symbol_info = {
            "symbol": "BTCUSDT",
            "filters": [
                {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "1000", "stepSize": "0.001"},
                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "maxQty": "1000", "stepSize": "0.001"},
                {"filterType": "MIN_NOTIONAL", "notional": "5"},
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


if __name__ == "__main__":
    unittest.main()
