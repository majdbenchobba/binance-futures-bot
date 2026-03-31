import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import (
    ALERT_BELL,
    KILL_SWITCH_FILE,
    MAX_DAILY_LOSS_PCT,
    MAX_OPEN_POSITIONS,
    STATE_FILE,
    SYMBOL_COOLDOWN_MINUTES,
)


def utc_now():
    return datetime.now(timezone.utc)


def current_session_date(now=None):
    active_now = now or utc_now()
    return active_now.date().isoformat()


def default_state():
    return {
        "session_date": "",
        "day_start_balance": 0.0,
        "last_trade_at": {},
        "halt_reason": "",
    }


def load_runtime_state(path=STATE_FILE):
    state_path = Path(path)
    if not state_path.exists():
        return default_state()

    try:
        with state_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logging.warning(f"Falling back to default runtime state because {path} could not be read: {exc}")
        return default_state()

    state = default_state()
    state.update(data)
    state["last_trade_at"] = dict(state.get("last_trade_at") or {})
    return state


def save_runtime_state(state, path=STATE_FILE):
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)


def emit_alert(message):
    logging.warning(message)
    if ALERT_BELL:
        print("\a", end="")


def get_wallet_balance(client, asset="USDT"):
    balances = client.futures_account_balance()
    for balance in balances:
        if balance.get("asset") == asset:
            return float(balance.get("balance") or 0.0)
    return 0.0


def get_open_position_symbols(client):
    positions = client.futures_position_information()
    return {
        position["symbol"]
        for position in positions
        if abs(float(position.get("positionAmt") or 0.0)) > 0.0
    }


def refresh_daily_state(state, wallet_balance, now=None):
    session_date = current_session_date(now=now)
    if state.get("session_date") != session_date:
        state["session_date"] = session_date
        state["day_start_balance"] = wallet_balance
        state["halt_reason"] = ""
    return state


def evaluate_daily_loss_limit(state, wallet_balance, max_daily_loss_pct=MAX_DAILY_LOSS_PCT):
    if max_daily_loss_pct <= 0:
        return ""

    starting_balance = float(state.get("day_start_balance") or 0.0)
    if starting_balance <= 0:
        return ""

    balance_floor = starting_balance * (1 - max_daily_loss_pct)
    if wallet_balance <= balance_floor:
        return (
            f"Daily loss guard triggered. Wallet balance {wallet_balance:.2f} "
            f"is at or below the limit {balance_floor:.2f}."
        )
    return ""


def has_manual_kill_switch(path=KILL_SWITCH_FILE):
    return Path(path).exists()


def evaluate_runtime_guardrails(client, state, now=None):
    wallet_balance = get_wallet_balance(client)
    refresh_daily_state(state, wallet_balance, now=now)

    if has_manual_kill_switch():
        reason = f"Manual kill switch detected at {KILL_SWITCH_FILE}. Bot will stop before placing new trades."
        state["halt_reason"] = reason
        return False, reason, wallet_balance

    reason = evaluate_daily_loss_limit(state, wallet_balance)
    if reason:
        state["halt_reason"] = reason
        return False, reason, wallet_balance

    state["halt_reason"] = ""
    return True, "", wallet_balance


def record_trade_opened(state, symbol, now=None):
    trade_time = (now or utc_now()).isoformat()
    state.setdefault("last_trade_at", {})
    state["last_trade_at"][symbol] = trade_time


def is_symbol_in_cooldown(state, symbol, cooldown_minutes=SYMBOL_COOLDOWN_MINUTES, now=None):
    if cooldown_minutes <= 0:
        return False

    trade_history = state.get("last_trade_at") or {}
    last_trade_at = trade_history.get(symbol)
    if not last_trade_at:
        return False

    try:
        last_trade_time = datetime.fromisoformat(last_trade_at)
    except ValueError:
        return False

    active_now = now or utc_now()
    return active_now < last_trade_time + timedelta(minutes=cooldown_minutes)


def can_open_new_trade(symbol, open_position_symbols, state, now=None):
    if symbol in open_position_symbols:
        return True, ""

    if MAX_OPEN_POSITIONS > 0 and len(open_position_symbols) >= MAX_OPEN_POSITIONS:
        return False, f"open position cap reached ({len(open_position_symbols)}/{MAX_OPEN_POSITIONS})"

    if is_symbol_in_cooldown(state, symbol, now=now):
        return False, f"{symbol} is still inside the cooldown window"

    return True, ""
