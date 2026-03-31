import logging
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from time import time

import numpy as np
from binance.exceptions import BinanceAPIException
from config import (
    DRY_RUN,
    ENTRY_INTERVAL,
    LEVERAGE,
    ORDER_RECV_WINDOW,
    PRICE_PROTECT,
    PROTECTION_WORKING_TYPE,
    REQUIRE_ONE_WAY_MODE,
    SMA_LONG,
    SMA_SHORT,
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
    TRADE_BALANCE_FRACTION,
)


_SYMBOL_INFO_CACHE = {}
PROTECTION_ORDER_TYPES = {"STOP_MARKET", "TAKE_PROFIT_MARKET"}


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


def quantize_value(raw_value: float, step_size: str, rounding=ROUND_DOWN) -> Decimal:
    quantity = _to_decimal(raw_value)
    step = _to_decimal(step_size)
    if step <= 0:
        return quantity
    steps = (quantity / step).quantize(Decimal("1"), rounding=rounding)
    return steps * step


def quantize_quantity(raw_quantity: float, step_size: str) -> Decimal:
    return quantize_value(raw_quantity, step_size, rounding=ROUND_DOWN)


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


def normalize_trigger_price(symbol_info, raw_price: float, rounding=ROUND_DOWN) -> Decimal:
    price_filter = get_filter(symbol_info, "PRICE_FILTER")
    if price_filter is None:
        return _to_decimal(raw_price)

    price = quantize_value(raw_price, price_filter["tickSize"], rounding=rounding)
    min_price = _to_decimal(price_filter["minPrice"])
    max_price = _to_decimal(price_filter["maxPrice"])

    if min_price > 0 and price < min_price:
        return min_price
    if max_price > 0 and price > max_price:
        return max_price
    return price


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

def get_position_snapshot(client, symbol):
    snapshot = {
        "symbol": symbol,
        "amount": 0.0,
        "entry_price": 0.0,
        "position_side": "BOTH",
        "has_position": False,
    }

    try:
        positions = client.futures_position_information(symbol=symbol)
        for pos in positions:
            if pos["symbol"] != symbol:
                continue

            amount = float(pos.get("positionAmt") or 0.0)
            snapshot.update(
                {
                    "amount": amount,
                    "entry_price": float(pos.get("entryPrice") or 0.0),
                    "position_side": pos.get("positionSide") or "BOTH",
                    "has_position": abs(amount) > 0.0,
                }
            )
            return snapshot
    except BinanceAPIException as e:
        logging.error(f"Error fetching position for {symbol}: {e}")
    return snapshot


def get_position(client, symbol):
    return get_position_snapshot(client, symbol)["amount"]


def get_open_orders(client, symbol):
    try:
        return client.futures_get_open_orders(symbol=symbol, recvWindow=ORDER_RECV_WINDOW)
    except BinanceAPIException as exc:
        logging.error(f"Error fetching open orders for {symbol}: {exc}")
        return []


def get_open_algo_orders(client, symbol):
    try:
        return client.futures_get_open_algo_orders(
            symbol=symbol,
            algoType="CONDITIONAL",
            recvWindow=ORDER_RECV_WINDOW,
        )
    except BinanceAPIException as exc:
        logging.error(f"Error fetching open algo orders for {symbol}: {exc}")
        return []


def _is_true(value) -> bool:
    return str(value).lower() == "true"


def get_order_type(order):
    return (order.get("orderType") or order.get("type") or order.get("origType") or "").upper()


def is_protection_order(order):
    order_type = get_order_type(order)
    return order_type in PROTECTION_ORDER_TYPES and (
        _is_true(order.get("closePosition"))
        or _is_true(order.get("reduceOnly"))
        or str(order.get("clientAlgoId") or order.get("clientOrderId") or "").startswith("sma_")
    )


def get_position_direction(position_amount: float) -> str:
    if position_amount > 0:
        return "LONG"
    if position_amount < 0:
        return "SHORT"
    return "FLAT"


def get_exit_side(position_amount: float):
    if position_amount > 0:
        return "SELL"
    if position_amount < 0:
        return "BUY"
    return None


def has_expected_protection_orders(open_orders, exit_side):
    active_pairs = {
        (get_order_type(order), (order.get("side") or "").upper())
        for order in open_orders
        if is_protection_order(order)
    }
    expected_pairs = {
        ("STOP_MARKET", exit_side.upper()),
        ("TAKE_PROFIT_MARKET", exit_side.upper()),
    }
    return expected_pairs.issubset(active_pairs)


def cancel_standard_orders(client, symbol, orders):
    if not orders:
        return 0

    if DRY_RUN:
        for order in orders:
            logging.info(
                f"[DRY RUN] Would cancel {order.get('type')} order {order.get('orderId')} on {symbol}"
            )
        return len(orders)

    cancelled = 0
    for order in orders:
        try:
            client.futures_cancel_order(
                symbol=symbol,
                orderId=order["orderId"],
                recvWindow=ORDER_RECV_WINDOW,
            )
            cancelled += 1
        except BinanceAPIException as exc:
            logging.error(
                f"Error cancelling order {order.get('orderId')} on {symbol}: {exc}"
            )
    return cancelled


def cancel_algo_orders(client, symbol, orders):
    if not orders:
        return 0

    if DRY_RUN:
        for order in orders:
            logging.info(
                f"[DRY RUN] Would cancel {get_order_type(order)} algo order {order.get('algoId')} on {symbol}"
            )
        return len(orders)

    cancelled = 0
    for order in orders:
        try:
            client.futures_cancel_algo_order(
                symbol=symbol,
                algoId=order["algoId"],
                recvWindow=ORDER_RECV_WINDOW,
            )
            cancelled += 1
        except BinanceAPIException as exc:
            logging.error(
                f"Error cancelling algo order {order.get('algoId')} on {symbol}: {exc}"
            )
    return cancelled


def cancel_protection_orders(client, symbol, open_orders=None):
    orders = open_orders if open_orders is not None else get_open_algo_orders(client, symbol)
    protection_orders = [order for order in orders if is_protection_order(order)]
    return cancel_algo_orders(client, symbol, protection_orders)


def build_protection_prices(symbol_info, position_amount: float, reference_price: float):
    reference = _to_decimal(reference_price)
    one = Decimal("1")
    stop_loss_pct = _to_decimal(STOP_LOSS_PCT)
    take_profit_pct = _to_decimal(TAKE_PROFIT_PCT)

    if reference <= 0:
        return None

    if STOP_LOSS_PCT <= 0 and TAKE_PROFIT_PCT <= 0:
        return None

    if position_amount > 0:
        stop_loss = normalize_trigger_price(
            symbol_info,
            reference * (one - stop_loss_pct),
            rounding=ROUND_DOWN,
        )
        take_profit = normalize_trigger_price(
            symbol_info,
            reference * (one + take_profit_pct),
            rounding=ROUND_UP,
        )
        if stop_loss >= reference or take_profit <= reference:
            return None
    elif position_amount < 0:
        stop_loss = normalize_trigger_price(
            symbol_info,
            reference * (one + stop_loss_pct),
            rounding=ROUND_UP,
        )
        take_profit = normalize_trigger_price(
            symbol_info,
            reference * (one - take_profit_pct),
            rounding=ROUND_DOWN,
        )
        if stop_loss <= reference or take_profit >= reference:
            return None
    else:
        return None

    return {"stop_loss": stop_loss, "take_profit": take_profit}

def set_leverage(client, symbol, leverage):
    if DRY_RUN:
        logging.info(f"[DRY RUN] Would set leverage to {leverage}x for {symbol}")
        return

    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        logging.info(f"Leverage set to {leverage}x for {symbol}")
    except BinanceAPIException as e:
        logging.error(f"Error setting leverage for {symbol}: {e}")

def place_order(
    client,
    symbol,
    side,
    quantity=None,
    reduce_only=False,
    order_type="MARKET",
    extra_params=None,
    response_type="RESULT",
):
    payload = {
        "symbol": symbol,
        "side": side,
        "type": order_type,
        "recvWindow": ORDER_RECV_WINDOW,
    }

    if quantity is not None:
        payload["quantity"] = quantity
    if reduce_only:
        payload["reduceOnly"] = "true"
    if response_type:
        payload["newOrderRespType"] = response_type
    if extra_params:
        payload.update(extra_params)

    if DRY_RUN:
        suffix = " reduce-only" if reduce_only else ""
        logging.info(f"[DRY RUN] Would place {side}{suffix} {order_type} order on {symbol}: {payload}")
        return {
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "dry_run": True,
            "reduce_only": reduce_only,
            "type": order_type,
            **(extra_params or {}),
        }

    try:
        order = client.futures_create_order(**payload)
        quantity_msg = f" for {quantity}" if quantity is not None else ""
        logging.info(f"Placed {side} {order_type} order{quantity_msg} on {symbol}")
        return order
    except BinanceAPIException as e:
        logging.error(f"Error placing {side} {order_type} order for {symbol}: {e}")
        return None


def get_order_fill_price(order, fallback_price: float) -> float:
    if not order:
        return fallback_price

    avg_price = float(order.get("avgPrice") or 0.0)
    if avg_price > 0:
        return avg_price

    executed_qty = float(order.get("executedQty") or 0.0)
    cum_quote = float(order.get("cumQuote") or 0.0)
    if executed_qty > 0 and cum_quote > 0:
        return cum_quote / executed_qty

    return fallback_price


def place_protective_orders(client, symbol, symbol_info, position_amount: float, reference_price: float):
    protection_prices = build_protection_prices(symbol_info, position_amount, reference_price)
    if protection_prices is None:
        logging.warning(f"Could not build protective prices for {symbol}.")
        return []

    exit_side = get_exit_side(position_amount)
    price_protect = "TRUE" if PRICE_PROTECT else "FALSE"
    timestamp_suffix = int(time() * 1000)

    stop_payload = {
        "algoType": "CONDITIONAL",
        "symbol": symbol,
        "side": exit_side,
        "type": "STOP_MARKET",
        "triggerPrice": float(protection_prices["stop_loss"]),
        "closePosition": "true",
        "workingType": PROTECTION_WORKING_TYPE,
        "priceProtect": price_protect,
        "clientAlgoId": f"sma_sl_{timestamp_suffix}"[:36],
        "recvWindow": ORDER_RECV_WINDOW,
    }
    take_payload = {
        "algoType": "CONDITIONAL",
        "symbol": symbol,
        "side": exit_side,
        "type": "TAKE_PROFIT_MARKET",
        "triggerPrice": float(protection_prices["take_profit"]),
        "closePosition": "true",
        "workingType": PROTECTION_WORKING_TYPE,
        "priceProtect": price_protect,
        "clientAlgoId": f"sma_tp_{timestamp_suffix}"[:36],
        "recvWindow": ORDER_RECV_WINDOW,
    }

    if DRY_RUN:
        logging.info(f"[DRY RUN] Would place {exit_side} STOP_MARKET algo order on {symbol}: {stop_payload}")
        logging.info(f"[DRY RUN] Would place {exit_side} TAKE_PROFIT_MARKET algo order on {symbol}: {take_payload}")
        stop_order = {"algoId": None, "side": exit_side, "orderType": "STOP_MARKET", **stop_payload}
        take_order = {"algoId": None, "side": exit_side, "orderType": "TAKE_PROFIT_MARKET", **take_payload}
    else:
        try:
            stop_order = client.futures_create_algo_order(**stop_payload)
            logging.info(f"Placed {exit_side} STOP_MARKET algo order on {symbol}")
        except BinanceAPIException as exc:
            logging.error(f"Error placing STOP_MARKET protection on {symbol}: {exc}")
            stop_order = None

        try:
            take_order = client.futures_create_algo_order(**take_payload)
            logging.info(f"Placed {exit_side} TAKE_PROFIT_MARKET algo order on {symbol}")
        except BinanceAPIException as exc:
            logging.error(f"Error placing TAKE_PROFIT_MARKET protection on {symbol}: {exc}")
            take_order = None

    if stop_order and take_order:
        direction = get_position_direction(position_amount).lower()
        logging.info(
            f"Protected {direction} {symbol} position with stop {protection_prices['stop_loss']} "
            f"and take profit {protection_prices['take_profit']}"
        )

    return [order for order in (stop_order, take_order) if order]


def ensure_position_protection(client, symbol, symbol_info, position_snapshot, fallback_price: float):
    protection_orders = get_open_algo_orders(client, symbol)
    protection_orders = [order for order in protection_orders if is_protection_order(order)]

    if not position_snapshot["has_position"]:
        if protection_orders:
            logging.info(f"Cancelling {len(protection_orders)} orphan protection orders on {symbol}")
            cancel_algo_orders(client, symbol, protection_orders)
        return []

    exit_side = get_exit_side(position_snapshot["amount"])
    if len(protection_orders) >= 2 and has_expected_protection_orders(protection_orders, exit_side):
        return protection_orders

    if protection_orders:
        logging.info(f"Refreshing incomplete protection orders on {symbol}")
        cancel_algo_orders(client, symbol, protection_orders)

    reference_price = position_snapshot["entry_price"] or fallback_price
    return place_protective_orders(
        client,
        symbol,
        symbol_info,
        position_snapshot["amount"],
        reference_price,
    )

def trade_symbol(client, symbol):
    if not ensure_supported_position_mode(client):
        return False

    symbol_info = get_symbol_info(client, symbol)
    if not symbol_info:
        logging.error(f"Missing exchange info for {symbol}")
        return False

    closes = get_klines(client, symbol, interval=ENTRY_INTERVAL)
    if closes is None:
        return False

    sma_short = calculate_sma(closes, SMA_SHORT)
    sma_long = calculate_sma(closes, SMA_LONG)

    if sma_short is None or sma_long is None:
        logging.info(f"Not enough data to calculate SMA for {symbol}")
        return False

    position_snapshot = get_position_snapshot(client, symbol)
    position = position_snapshot["amount"]
    last_price = closes[-1]

    set_leverage(client, symbol, LEVERAGE)

    try:
        if sma_short > sma_long and position <= 0:
            signal_side = "BUY"
        elif sma_short < sma_long and position >= 0:
            signal_side = "SELL"
        else:
            logging.info(f"No trade signal for {symbol}")
            ensure_position_protection(
                client,
                symbol,
                symbol_info,
                position_snapshot,
                fallback_price=last_price,
            )
            return False

        if position_snapshot["has_position"]:
            cancel_protection_orders(client, symbol)
            close_qty = normalize_order_quantity(symbol_info, abs(position))
            if close_qty > 0:
                logging.info(f"Closing {get_position_direction(position).lower()} position on {symbol}")
                place_order(
                    client,
                    symbol,
                    get_exit_side(position),
                    float(close_qty),
                    reduce_only=True,
                )
            else:
                logging.warning(f"Existing position on {symbol} could not be normalized for closing.")

        usdt_balance = get_available_usdt_balance(client)
        if usdt_balance <= 0:
            logging.warning("No available USDT balance for trading.")
            return False

        trade_amount_usdt = usdt_balance * TRADE_BALANCE_FRACTION
        raw_quantity = trade_amount_usdt / last_price
        quantity = normalize_order_quantity(symbol_info, raw_quantity)

        if quantity <= 0:
            logging.warning(f"Calculated quantity for {symbol} is below the symbol minimum.")
            return False

        if not passes_min_notional(symbol_info, quantity, last_price):
            logging.warning(f"Calculated notional for {symbol} is below Binance minimum notional.")
            return False

        direction_label = "LONG" if signal_side == "BUY" else "SHORT"
        logging.info(f"Going {direction_label} on {symbol}")
        entry_order = place_order(client, symbol, signal_side, float(quantity))
        if entry_order is None:
            return False

        signed_amount = float(quantity) if signal_side == "BUY" else -float(quantity)
        fill_price = get_order_fill_price(entry_order, last_price)
        place_protective_orders(client, symbol, symbol_info, signed_amount, fill_price)
        return not DRY_RUN

    except Exception as e:
        logging.error(f"Error in trade_symbol for {symbol}: {e}")
        return False
