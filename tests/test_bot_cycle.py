import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot import build_cycle_symbols


class BotCycleTest(unittest.TestCase):
    def test_build_cycle_symbols_preserves_scan_priority_and_adds_open_positions(self):
        trade_symbols, reconcile_only_symbols = build_cycle_symbols(
            ["BTCUSDT", "SOLUSDT"],
            {"ETHUSDT", "BTCUSDT"},
            {"ADAUSDT", "ETHUSDT"},
        )

        self.assertEqual(trade_symbols, ["BTCUSDT", "SOLUSDT", "ETHUSDT"])
        self.assertEqual(reconcile_only_symbols, ["ADAUSDT"])


if __name__ == "__main__":
    unittest.main()
