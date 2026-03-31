from config import ALERT_ON_POSITION_CHANGES, REPORT_EVERY_CYCLES
from trading import get_all_open_algo_orders, is_protection_order


def _safe_float(value):
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def count_protection_orders_by_symbol(open_algo_orders):
    counts = {}
    for order in open_algo_orders:
        if not is_protection_order(order):
            continue
        symbol = order.get("symbol")
        if not symbol:
            continue
        counts[symbol] = counts.get(symbol, 0) + 1
    return counts


def extract_open_positions(position_rows, protection_counts=None):
    protection_counts = protection_counts or {}
    positions = []
    for row in position_rows:
        amount = _safe_float(row.get("positionAmt"))
        if abs(amount) <= 0.0:
            continue

        positions.append(
            {
                "symbol": row.get("symbol", ""),
                "side": "LONG" if amount > 0 else "SHORT",
                "quantity": abs(amount),
                "entry_price": _safe_float(row.get("entryPrice")),
                "mark_price": _safe_float(row.get("markPrice")),
                "unrealized_pnl": _safe_float(row.get("unRealizedProfit")),
                "notional": _safe_float(row.get("notional")),
                "liquidation_price": _safe_float(row.get("liquidationPrice")),
                "leverage": int(_safe_float(row.get("leverage"))),
                "protection_count": protection_counts.get(row.get("symbol", ""), 0),
            }
        )

    return sorted(positions, key=lambda item: item["symbol"])


def get_balance_snapshot(client, asset="USDT"):
    balances = client.futures_account_balance()
    for balance in balances:
        if balance.get("asset") != asset:
            continue
        return {
            "asset": asset,
            "wallet_balance": _safe_float(balance.get("balance")),
            "available_balance": _safe_float(balance.get("availableBalance")),
            "cross_wallet_balance": _safe_float(balance.get("crossWalletBalance")),
            "cross_unrealized_pnl": _safe_float(balance.get("crossUnPnl")),
            "max_withdraw_amount": _safe_float(balance.get("maxWithdrawAmount")),
        }
    return {
        "asset": asset,
        "wallet_balance": 0.0,
        "available_balance": 0.0,
        "cross_wallet_balance": 0.0,
        "cross_unrealized_pnl": 0.0,
        "max_withdraw_amount": 0.0,
    }


def build_account_snapshot(client):
    open_algo_orders = get_all_open_algo_orders(client)
    protection_counts = count_protection_orders_by_symbol(open_algo_orders)
    positions = extract_open_positions(
        client.futures_position_information(),
        protection_counts=protection_counts,
    )
    balance = get_balance_snapshot(client)

    return {
        "balance": balance,
        "positions": positions,
        "open_position_count": len(positions),
        "total_unrealized_pnl": round(sum(item["unrealized_pnl"] for item in positions), 8),
        "protection_order_count": sum(protection_counts.values()),
        "protection_counts": protection_counts,
    }


def build_position_signature(snapshot):
    position_parts = [
        (
            position["symbol"],
            position["side"],
            round(position["quantity"], 8),
            round(position["entry_price"], 8),
            int(position["protection_count"]),
        )
        for position in snapshot.get("positions", [])
    ]
    orphan_protection_parts = sorted(
        (
            symbol,
            count,
        )
        for symbol, count in snapshot.get("protection_counts", {}).items()
        if symbol not in {position["symbol"] for position in snapshot.get("positions", [])}
    )
    return repr((tuple(sorted(position_parts)), tuple(orphan_protection_parts)))


def empty_position_signature():
    return build_position_signature({"positions": [], "protection_counts": {}})


def increment_cycle_count(state):
    state["cycle_count"] = int(state.get("cycle_count") or 0) + 1
    return state["cycle_count"]


def should_log_cycle_report(state, state_changed, report_every_cycles=REPORT_EVERY_CYCLES):
    cycle_count = int(state.get("cycle_count") or 0)
    if state_changed:
        return True
    if report_every_cycles <= 1:
        return True
    return cycle_count % report_every_cycles == 0


def should_alert_on_position_change(state, new_signature, alert_on_position_changes=ALERT_ON_POSITION_CHANGES):
    if not alert_on_position_changes:
        return False
    previous_signature = state.get("last_position_signature", "")
    if not previous_signature and new_signature == empty_position_signature():
        return False
    return previous_signature != new_signature


def remember_position_signature(state, signature):
    state["last_position_signature"] = signature


def format_cycle_summary(snapshot, cycle_count):
    balance = snapshot["balance"]
    return (
        f"Cycle {cycle_count}: wallet={balance['wallet_balance']:.2f} "
        f"available={balance['available_balance']:.2f} "
        f"uPnL={snapshot['total_unrealized_pnl']:.2f} "
        f"open_positions={snapshot['open_position_count']} "
        f"protection_orders={snapshot['protection_order_count']}"
    )


def format_position_lines(snapshot):
    lines = []
    for position in snapshot.get("positions", []):
        line = (
            f"{position['symbol']} {position['side']} qty={position['quantity']:.6f} "
            f"entry={position['entry_price']:.4f} mark={position['mark_price']:.4f} "
            f"uPnL={position['unrealized_pnl']:.4f}"
        )
        if position["leverage"] > 0:
            line += f" lev={position['leverage']}x"
        line += f" protections={position['protection_count']}"
        if position["liquidation_price"] > 0:
            line += f" liq={position['liquidation_price']:.4f}"
        lines.append(line)
    return lines


def build_alert_context(snapshot, cycle_count):
    return {
        "event": "position_state_changed",
        "cycle_count": cycle_count,
        "wallet_balance": snapshot["balance"]["wallet_balance"],
        "available_balance": snapshot["balance"]["available_balance"],
        "total_unrealized_pnl": snapshot["total_unrealized_pnl"],
        "positions": snapshot["positions"],
        "protection_order_count": snapshot["protection_order_count"],
    }
