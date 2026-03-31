import os

from dotenv import load_dotenv


load_dotenv()

API_KEY = os.getenv("BINANCE_API_KEY", "")
API_SECRET = os.getenv("BINANCE_API_SECRET", "")

USE_TESTNET = os.getenv("USE_TESTNET", "true").lower() == "true"
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
RUN_ONCE = os.getenv("RUN_ONCE", "false").lower() == "true"
ENTRY_INTERVAL = os.getenv("ENTRY_INTERVAL", "1m")
LEVERAGE = int(os.getenv("LEVERAGE", "20"))
SMA_SHORT = int(os.getenv("SMA_SHORT", "7"))
SMA_LONG = int(os.getenv("SMA_LONG", "25"))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "0.01"))
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "0.02"))
PROTECTION_WORKING_TYPE = os.getenv("PROTECTION_WORKING_TYPE", "MARK_PRICE").upper()
PRICE_PROTECT = os.getenv("PRICE_PROTECT", "true").lower() == "true"
TOP_N_SYMBOLS = int(os.getenv("TOP_N_SYMBOLS", "3"))
VOLATILITY_INTERVAL = os.getenv("VOLATILITY_INTERVAL", "1h")
VOLATILITY_LOOKBACK = int(os.getenv("VOLATILITY_LOOKBACK", "24"))
SYMBOL_ALLOWLIST = [
    symbol.strip().upper()
    for symbol in os.getenv("SYMBOL_ALLOWLIST", "").split(",")
    if symbol.strip()
]
MAX_SYMBOL_SCAN = int(os.getenv("MAX_SYMBOL_SCAN", "0"))
TRADE_BALANCE_FRACTION = float(os.getenv("TRADE_BALANCE_FRACTION", "0.01"))
ORDER_RECV_WINDOW = int(os.getenv("ORDER_RECV_WINDOW", "5000"))
REQUIRE_ONE_WAY_MODE = os.getenv("REQUIRE_ONE_WAY_MODE", "true").lower() == "true"
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "1"))
SYMBOL_COOLDOWN_MINUTES = int(os.getenv("SYMBOL_COOLDOWN_MINUTES", "30"))
MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", "0.03"))
STATE_FILE = os.getenv("STATE_FILE", "runtime/state.json")
KILL_SWITCH_FILE = os.getenv("KILL_SWITCH_FILE", "runtime/KILL_SWITCH")
ALERT_BELL = os.getenv("ALERT_BELL", "false").lower() == "true"
LOOP_SLEEP_SECONDS = int(os.getenv("LOOP_SLEEP_SECONDS", "60"))
LOG_FILE = os.getenv("LOG_FILE", "logs/bot.log")
