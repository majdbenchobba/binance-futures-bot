import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from risk_controls import (
    can_open_new_trade,
    current_session_date,
    default_state,
    evaluate_daily_loss_limit,
    has_manual_kill_switch,
    is_symbol_in_cooldown,
    load_runtime_state,
    record_trade_opened,
    refresh_daily_state,
    save_runtime_state,
)


class RiskControlsTest(unittest.TestCase):
    def test_refresh_daily_state_resets_reference_balance_on_new_day(self):
        state = default_state()
        now = datetime(2026, 3, 31, 12, 0, tzinfo=timezone.utc)

        refresh_daily_state(state, 125.0, now=now)

        self.assertEqual(state["session_date"], current_session_date(now=now))
        self.assertEqual(state["day_start_balance"], 125.0)

    def test_daily_loss_limit_triggers_when_balance_falls_below_floor(self):
        state = default_state()
        state["day_start_balance"] = 100.0

        reason = evaluate_daily_loss_limit(state, 98.0, max_daily_loss_pct=0.03)
        self.assertEqual(reason, "")

        reason = evaluate_daily_loss_limit(state, 97.0, max_daily_loss_pct=0.02)
        self.assertIn("Daily loss guard triggered", reason)

    def test_record_trade_opened_sets_symbol_cooldown(self):
        state = default_state()
        now = datetime(2026, 3, 31, 12, 0, tzinfo=timezone.utc)

        record_trade_opened(state, "ETHUSDT", now=now)

        self.assertTrue(is_symbol_in_cooldown(state, "ETHUSDT", cooldown_minutes=30, now=now))
        later = datetime(2026, 3, 31, 12, 31, tzinfo=timezone.utc)
        self.assertFalse(is_symbol_in_cooldown(state, "ETHUSDT", cooldown_minutes=30, now=later))

    def test_can_open_new_trade_blocks_when_position_cap_is_reached(self):
        state = default_state()
        allowed, reason = can_open_new_trade("ETHUSDT", {"BTCUSDT"}, state)
        self.assertFalse(allowed)
        self.assertIn("open position cap reached", reason)

    def test_can_open_new_trade_allows_existing_open_symbol(self):
        state = default_state()
        allowed, reason = can_open_new_trade("BTCUSDT", {"BTCUSDT"}, state)
        self.assertTrue(allowed)
        self.assertEqual(reason, "")

    def test_runtime_state_round_trip(self):
        state = default_state()
        state["day_start_balance"] = 150.0
        state["last_trade_at"]["BTCUSDT"] = "2026-03-31T12:00:00+00:00"

        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "state.json"
            save_runtime_state(state, path=path)
            loaded = load_runtime_state(path=path)

        self.assertEqual(loaded["day_start_balance"], 150.0)
        self.assertEqual(loaded["last_trade_at"]["BTCUSDT"], "2026-03-31T12:00:00+00:00")

    def test_manual_kill_switch_detects_existing_file(self):
        with TemporaryDirectory() as tmp_dir:
            kill_file = Path(tmp_dir) / "KILL_SWITCH"
            kill_file.write_text("stop", encoding="utf-8")
            self.assertTrue(has_manual_kill_switch(path=kill_file))


if __name__ == "__main__":
    unittest.main()
