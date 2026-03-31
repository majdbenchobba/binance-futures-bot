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
from risk_controls import (
    can_open_new_trade,
    emit_alert,
    evaluate_runtime_guardrails,
    get_open_position_symbols,
    load_runtime_state,
    record_trade_opened,
    save_runtime_state,
)
from trading import trade_symbol


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
                emit_alert(halt_reason)
                logger.warning(f"Last known wallet balance: {wallet_balance:.2f} USDT")
                break

            top_symbols = get_top_volatile_symbols(
                client,
                top_n=TOP_N_SYMBOLS,
                interval=VOLATILITY_INTERVAL,
                lookback=VOLATILITY_LOOKBACK,
            )
            logger.info(f"Top volatile symbols: {top_symbols}")

            for symbol in top_symbols:
                try:
                    open_position_symbols = get_open_position_symbols(client)
                    can_open, skip_reason = can_open_new_trade(
                        symbol,
                        open_position_symbols,
                        runtime_state,
                    )
                    if not can_open:
                        logger.warning(f"Skipping {symbol}: {skip_reason}")
                        continue

                    entered_position = trade_symbol(client, symbol)
                    if entered_position:
                        record_trade_opened(runtime_state, symbol)
                        save_runtime_state(runtime_state)
                except Exception as e:
                    logger.error(f"Error trading {symbol}: {e}")

            if RUN_ONCE:
                logger.info("RUN_ONCE enabled. Exiting after a single scan cycle.")
                break

            time.sleep(LOOP_SLEEP_SECONDS)

        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            time.sleep(LOOP_SLEEP_SECONDS)


if __name__ == "__main__":
    main()
