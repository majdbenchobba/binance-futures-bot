import time
from binance.client import Client
from config import (
    API_KEY,
    API_SECRET,
    LOOP_SLEEP_SECONDS,
    TOP_N_SYMBOLS,
    USE_TESTNET,
    VOLATILITY_INTERVAL,
    VOLATILITY_LOOKBACK,
)
from logger import setup_logger
from data_utils import get_top_volatile_symbols
from trading import trade_symbol


def create_client(api_key, api_secret, use_testnet):
    client = Client(api_key, api_secret, testnet=use_testnet)
    if use_testnet:
        client.API_URL = "https://testnet.binancefuture.com/fapi/v1"
        client.FUTURES_URL = "https://testnet.binancefuture.com/fapi/v1"
    return client


def main():
    logger = setup_logger()
    logger.info("Starting Binance Futures SMA crossover bot")

    if not API_KEY or not API_SECRET:
        logger.error("Missing Binance API credentials. Add them to your .env file first.")
        return

    client = create_client(API_KEY, API_SECRET, USE_TESTNET)

    while True:
        try:
            top_symbols = get_top_volatile_symbols(
                client,
                top_n=TOP_N_SYMBOLS,
                interval=VOLATILITY_INTERVAL,
                lookback=VOLATILITY_LOOKBACK,
            )
            logger.info(f"Top volatile symbols: {top_symbols}")

            for symbol in top_symbols:
                try:
                    trade_symbol(client, symbol)
                except Exception as e:
                    logger.error(f"Error trading {symbol}: {e}")

            time.sleep(LOOP_SLEEP_SECONDS)

        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            time.sleep(LOOP_SLEEP_SECONDS)


if __name__ == "__main__":
    main()
