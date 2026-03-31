import time
import sys
from binance.client import Client
from config import (
    API_KEY,
    API_SECRET,
    DRY_RUN,
    LOOP_SLEEP_SECONDS,
    RUN_ONCE,
    TOP_N_SYMBOLS,
    USE_TESTNET,
    VOLATILITY_INTERVAL,
    VOLATILITY_LOOKBACK,
)
from journal import append_journal_entry
from logger import setup_logger
from data_utils import get_top_volatile_symbols
from notifications import send_alert
from reporting import (
    build_account_snapshot,
    build_alert_context,
    build_position_signature,
    format_cycle_summary,
    format_position_lines,
    increment_cycle_count,
    remember_position_signature,
    should_alert_on_position_change,
    should_log_cycle_report,
)
from risk_controls import (
    can_open_new_trade,
    evaluate_runtime_guardrails,
    get_open_position_symbols,
    load_runtime_state,
    record_trade_opened,
    save_runtime_state,
)
from trading import get_open_protection_symbols, reconcile_symbol_protection, trade_symbol


def _unique_symbols(*symbol_groups):
    ordered_symbols = []
    seen = set()
    for group in symbol_groups:
        for symbol in group:
            if symbol in seen:
                continue
            seen.add(symbol)
            ordered_symbols.append(symbol)
    return ordered_symbols


def build_cycle_symbols(top_symbols, open_position_symbols, protection_symbols):
    trade_symbols = _unique_symbols(top_symbols, sorted(open_position_symbols))
    trade_symbol_set = set(trade_symbols)
    reconcile_only_symbols = [
        symbol
        for symbol in sorted(protection_symbols)
        if symbol not in trade_symbol_set and symbol not in open_position_symbols
    ]
    return trade_symbols, reconcile_only_symbols


def create_client(api_key, api_secret, use_testnet):
    client = Client(api_key, api_secret, testnet=use_testnet)
    if use_testnet:
        client.API_URL = "https://testnet.binancefuture.com/fapi/v1"
        client.FUTURES_URL = "https://testnet.binancefuture.com/fapi/v1"
    return client


def main(max_cycles=None, sleep_seconds=None):
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    logger = setup_logger()
    logger.info("Starting Binance Futures SMA crossover bot")
    if DRY_RUN:
        logger.info("Dry run mode is enabled. No live orders will be placed.")

    if not API_KEY or not API_SECRET:
        logger.error("Missing Binance API credentials. Add them to your .env file first.")
        return

    client = create_client(API_KEY, API_SECRET, USE_TESTNET)
    runtime_state = load_runtime_state()
    completed_cycles = 0
    effective_sleep_seconds = LOOP_SLEEP_SECONDS if sleep_seconds is None else sleep_seconds

    while True:
        try:
            can_trade, halt_reason, wallet_balance = evaluate_runtime_guardrails(client, runtime_state)
            save_runtime_state(runtime_state)

            if not can_trade:
                send_alert(
                    halt_reason,
                    level="warning",
                    context={"event": "guardrail_halt", "wallet_balance": wallet_balance},
                    log_message=False,
                )
                append_journal_entry(
                    "guardrail_halt",
                    {"reason": halt_reason, "wallet_balance": wallet_balance},
                )
                logger.warning(f"Last known wallet balance: {wallet_balance:.2f} USDT")
                break

            top_symbols = get_top_volatile_symbols(
                client,
                top_n=TOP_N_SYMBOLS,
                interval=VOLATILITY_INTERVAL,
                lookback=VOLATILITY_LOOKBACK,
            )
            logger.info(f"Top volatile symbols: {top_symbols}")
            open_position_symbols = get_open_position_symbols(client)
            protection_symbols = get_open_protection_symbols(client)
            trade_symbols, reconcile_only_symbols = build_cycle_symbols(
                top_symbols,
                open_position_symbols,
                protection_symbols,
            )
            logger.info(
                f"Managing symbols this cycle: trade={trade_symbols} reconcile_only={reconcile_only_symbols}"
            )

            for symbol in trade_symbols:
                try:
                    current_open_position_symbols = get_open_position_symbols(client)
                    can_open, skip_reason = can_open_new_trade(
                        symbol,
                        current_open_position_symbols,
                        runtime_state,
                    )
                    if not can_open:
                        logger.warning(f"Skipping {symbol}: {skip_reason}")
                        continue

                    entered_position = trade_symbol(
                        client,
                        symbol,
                        allow_new_entries=symbol in top_symbols,
                    )
                    if entered_position:
                        record_trade_opened(runtime_state, symbol)
                        save_runtime_state(runtime_state)
                        append_journal_entry(
                            "live_position_opened",
                            {"symbol": symbol, "cycle_count": int(runtime_state.get("cycle_count") or 0) + 1},
                        )
                        send_alert(
                            f"Opened live position on {symbol}",
                            level="info",
                            context={"event": "position_opened", "symbol": symbol},
                            log_message=False,
                        )
                except Exception as e:
                    message = f"Error trading {symbol}: {e}"
                    logger.error(message)
                    append_journal_entry(
                        "trade_error",
                        {"symbol": symbol, "message": message},
                    )
                    send_alert(
                        message,
                        level="error",
                        context={"event": "trade_error", "symbol": symbol},
                        log_message=False,
                    )

            for symbol in reconcile_only_symbols:
                try:
                    reconcile_symbol_protection(client, symbol)
                except Exception as e:
                    message = f"Error reconciling orphan protection on {symbol}: {e}"
                    logger.error(message)
                    append_journal_entry(
                        "reconcile_error",
                        {"symbol": symbol, "message": message},
                    )
                    send_alert(
                        message,
                        level="error",
                        context={"event": "reconcile_error", "symbol": symbol},
                        log_message=False,
                    )

            cycle_count = increment_cycle_count(runtime_state)
            account_snapshot = build_account_snapshot(client)
            position_signature = build_position_signature(account_snapshot)
            state_changed = should_alert_on_position_change(runtime_state, position_signature)

            if should_log_cycle_report(runtime_state, state_changed):
                logger.info(format_cycle_summary(account_snapshot, cycle_count))
                for line in format_position_lines(account_snapshot):
                    logger.info(line)

            append_journal_entry(
                "cycle_summary",
                {
                    "cycle_count": cycle_count,
                    "summary": format_cycle_summary(account_snapshot, cycle_count),
                    "trade_symbols": trade_symbols,
                    "reconcile_only_symbols": reconcile_only_symbols,
                    "snapshot": account_snapshot,
                },
            )

            if state_changed:
                position_lines = format_position_lines(account_snapshot)
                if position_lines:
                    message = f"Position state changed: {' | '.join(position_lines)}"
                else:
                    message = "Position state changed: account is flat."
                append_journal_entry(
                    "position_state_changed",
                    {
                        "cycle_count": cycle_count,
                        "snapshot": account_snapshot,
                        "position_lines": position_lines,
                    },
                )
                send_alert(
                    message,
                    level="info",
                    context=build_alert_context(account_snapshot, cycle_count),
                    log_message=False,
                )

            remember_position_signature(runtime_state, position_signature)
            save_runtime_state(runtime_state)
            completed_cycles += 1

            if RUN_ONCE:
                logger.info("RUN_ONCE enabled. Exiting after a single scan cycle.")
                break
            if max_cycles is not None and completed_cycles >= max_cycles:
                logger.info(f"Reached requested cycle limit ({max_cycles}). Exiting.")
                break

            time.sleep(effective_sleep_seconds)

        except Exception as e:
            message = f"Error in main loop: {e}"
            logger.error(message)
            append_journal_entry("main_loop_error", {"message": message})
            send_alert(
                message,
                level="error",
                context={"event": "main_loop_error"},
                log_message=False,
            )
            time.sleep(effective_sleep_seconds)


if __name__ == "__main__":
    main()
