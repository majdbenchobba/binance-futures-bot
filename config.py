import os

from dotenv import load_dotenv


load_dotenv()

API_KEY = os.getenv("BINANCE_API_KEY", "")
API_SECRET = os.getenv("BINANCE_API_SECRET", "")

USE_TESTNET = os.getenv("USE_TESTNET", "true").lower() == "true"
LEVERAGE = int(os.getenv("LEVERAGE", "20"))
SMA_SHORT = int(os.getenv("SMA_SHORT", "7"))
SMA_LONG = int(os.getenv("SMA_LONG", "25"))
TOP_N_SYMBOLS = int(os.getenv("TOP_N_SYMBOLS", "3"))
VOLATILITY_INTERVAL = os.getenv("VOLATILITY_INTERVAL", "1h")
VOLATILITY_LOOKBACK = int(os.getenv("VOLATILITY_LOOKBACK", "24"))
TRADE_BALANCE_FRACTION = float(os.getenv("TRADE_BALANCE_FRACTION", "0.01"))
LOOP_SLEEP_SECONDS = int(os.getenv("LOOP_SLEEP_SECONDS", "60"))
LOG_FILE = os.getenv("LOG_FILE", "logs/bot.log")
