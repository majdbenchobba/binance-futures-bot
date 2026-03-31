import logging
from decimal import Decimal, ROUND_DOWN

import numpy as np
from binance.exceptions import BinanceAPIException
from config import (
    DRY_RUN,
    ENTRY_INTERVAL,
    LEVERAGE,
    ORDER_RECV_WINDOW,
    REQUIRE_ONE_WAY_MODE,
    SMA_LONG,
    SMA_SHORT,
    TRADE_BALANCE_FRACTION,
)


_SYMBOL_INFO_CACHE = {}


def _to_decimal(value) -> Decimal:
    return Decimal(str(value))


def get_symbol_info(client, symbol):
    cached = _SYMBOL_INFO_CACHE.get(symbol)
    if cached:
        return cached

    info = client.futures_exchange_info()
    symbol_map = {entry["symbol"]: entry for entry in info["symbols"]}
    _SYMBOL_INFO_CACHE.update(symbol_map)
    return _SYMBOL_INFO_CACHE.get(symbol)


def get_filter(symbol_info, filter_type):
    for filter_data in symbol_info.get("filters", []):
        if filter_data.get("filterType") == filter_type:
            return filter_data
    return None


def quantize_quantity(raw_quantity: float, step_size: str) -> Decimal:
    quantity = _to_decimal(raw_quantity)
    step = _to_decimal(step_size)
    if step <= 0:
        return quantity
    steps = (quantity / step).quantize(Decimal("1"), rounding=ROUND_DOWN)
    return steps * step


def normalize_order_quantity(symbol_info, raw_quantity: float, use_market_limits: bool = True) -> Decimal:
    quantity_filter = None
    if use_market_limits:
        quantity_filter = get_filter(symbol_info, "MARKET_LOT_SIZE")
    if quantity_filter is None:
        quantity_filter = get_filter(symbol_info, "LOT_SIZE")
    if quantity_filter is None:
        raise ValueError(f"Missing quantity filter for {symbol_info['symbol']}")

    min_qty = _to_decimal(quantity_filter["minQty"])
    max_qty = _to_decimal(quantity_filter["maxQty"])
    quantity = quantize_quantity(raw_quantity, quantity_filter["stepSize"])

    if quantity < min_qty:
        return Decimal("0")
    if quantity > max_qty:
        return max_qty
    return quantity


def passes_min_notional(symbol_info, quantity: Decimal, price: float) -> bool:
    min_notional_filter = get_filter(symbol_info, "MIN_NOTIONAL")
    if min_notional_filter is None:
        return True
    min_notional = _to_decimal(min_notional_filter["notional"])
    notional = quantity * _to_decimal(price)
    return notional >= min_notional


def get_available_usdt_balance(client) -> float:
    balance_info = client.futures_account_balance()
    for asset in balance_info:
        if asset.get("asset") == "USDT":
            return float(asset.get("availableBalance") or asset.get("balance") or 0.0)
    return 0.0


def ensure_supported_position_mode(client) -> bool:
    try:
        position_mode = client.futures_get_position_mode()
    except Exception as exc:
        logging.error(f"Unable to check position mode: {exc}")
        return False

    dual_side = str(position_mode.get("dualSidePosition", "false")).lower() == "true"
    if dual_side and REQUIRE_ONE_WAY_MODE:
        logging.error("Account is in hedge mode. Switch to one-way mode before using this bot.")
        return False

    return True


def get_klines(client, symbol, interval='1m', limit=100):
    try:
        klines = client.futures_klines(symbol=symbol, interval=interval, limit=limit)
        closes = np.array([float(k[4]) for k in klines])
        return closes
    except Exception as e:
        logging.error(f"Error fetching klines for {symbol}: {e}")
        return None

def calculate_sma(prices, period):
    if prices is None or len(prices) < period:
        return None
    return np.mean(prices[-period:])

def get_position(client, symbol):
    try:
        positions = client.futures_position_information(symbol=symbol)
        for pos in positions:
            if pos['symbol'] == symbol:
                return float(pos['positionAmt'])
    except BinanceAPIException as e:
        logging.error(f"Error fetching position for {symbol}: {e}")
    return 0.0

def set_leverage(client, symbol, leverage):
    if DRY_RUN:
        logging.info(f"[DRY RUN] Would set leverage to {leverage}x for {symbol}")
        return

    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        logging.info(f"Leverage set to {leverage}x for {symbol}")
    except BinanceAPIException as e:
        logging.error(f"Error setting leverage for {symbol}: {e}")

def place_order(client, symbol, side, quantity, reduce_only=False):
    if DRY_RUN:
        suffix = " reduce-only" if reduce_only else ""
        logging.info(f"[DRY RUN] Would place {side}{suffix} order for {quantity} {symbol}")
        return {
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "dry_run": True,
            "reduce_only": reduce_only,
        }

    try:
        order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type='MARKET',
            quantity=quantity,
            reduceOnly="true" if reduce_only else "false",
            recvWindow=ORDER_RECV_WINDOW,
            newOrderRespType="RESULT",
        )
        logging.info(f"Placed {side} order for {quantity} {symbol}")
        return order
    except BinanceAPIException as e:
        logging.error(f"Error placing order {side} for {symbol}: {e}")
        return None

def trade_symbol(client, symbol):
    if not ensure_supported_position_mode(client):
        return

    symbol_info = get_symbol_info(client, symbol)
    if not symbol_info:
        logging.error(f"Missing exchange info for {symbol}")
        return

    closes = get_klines(client, symbol, interval=ENTRY_INTERVAL)
    if closes is None:
        return

    sma_short = calculate_sma(closes, SMA_SHORT)
    sma_long = calculate_sma(closes, SMA_LONG)

    if sma_short is None or sma_long is None:
        logging.info(f"Not enough data to calculate SMA for {symbol}")
        return

    position = get_position(client, symbol)
    last_price = closes[-1]

    set_leverage(client, symbol, LEVERAGE)

    try:
        usdt_balance = get_available_usdt_balance(client)
        if usdt_balance <= 0:
            logging.warning("No available USDT balance for trading.")
            return

        trade_amount_usdt = usdt_balance * TRADE_BALANCE_FRACTION
        raw_quantity = trade_amount_usdt / last_price
        quantity = normalize_order_quantity(symbol_info, raw_quantity)

        if quantity <= 0:
            logging.warning(f"Calculated quantity for {symbol} is below the symbol minimum.")
            return

        if not passes_min_notional(symbol_info, quantity, last_price):
            logging.warning(f"Calculated notional for {symbol} is below Binance minimum notional.")
            return

        if sma_short > sma_long and position <= 0:
            if position < 0:
                logging.info(f"Closing short position on {symbol}")
                close_qty = normalize_order_quantity(symbol_info, abs(position))
                if close_qty > 0:
                    place_order(client, symbol, 'BUY', float(close_qty), reduce_only=True)

            logging.info(f"Going LONG on {symbol}")
            place_order(client, symbol, 'BUY', float(quantity))

        elif sma_short < sma_long and position >= 0:
            if position > 0:
                logging.info(f"Closing long position on {symbol}")
                close_qty = normalize_order_quantity(symbol_info, abs(position))
                if close_qty > 0:
                    place_order(client, symbol, 'SELL', float(close_qty), reduce_only=True)

            logging.info(f"Going SHORT on {symbol}")
            place_order(client, symbol, 'SELL', float(quantity))

        else:
            logging.info(f"No trade signal for {symbol}")

    except Exception as e:
        logging.error(f"Error in trade_symbol for {symbol}: {e}")
