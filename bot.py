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
from logger import setup_logger
from data_utils import get_top_volatile_symbols
from notifications import send_alert
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


def main():
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
                        send_alert(
                            f"Opened live position on {symbol}",
                            level="info",
                            context={"event": "position_opened", "symbol": symbol},
                            log_message=False,
                        )
                except Exception as e:
                    message = f"Error trading {symbol}: {e}"
                    logger.error(message)
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
                    send_alert(
                        message,
                        level="error",
                        context={"event": "reconcile_error", "symbol": symbol},
                        log_message=False,
                    )

            if RUN_ONCE:
                logger.info("RUN_ONCE enabled. Exiting after a single scan cycle.")
                break

            time.sleep(LOOP_SLEEP_SECONDS)

        except Exception as e:
            message = f"Error in main loop: {e}"
            logger.error(message)
            send_alert(
                message,
                level="error",
                context={"event": "main_loop_error"},
                log_message=False,
            )
            time.sleep(LOOP_SLEEP_SECONDS)


if __name__ == "__main__":
    main()
