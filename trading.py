import numpy as np
from binance.exceptions import BinanceAPIException
from config import DRY_RUN, LEVERAGE, SMA_LONG, SMA_SHORT, TRADE_BALANCE_FRACTION
import logging


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
    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        logging.info(f"Leverage set to {leverage}x for {symbol}")
    except BinanceAPIException as e:
        logging.error(f"Error setting leverage for {symbol}: {e}")

def place_order(client, symbol, side, quantity):
    if DRY_RUN:
        logging.info(f"[DRY RUN] Would place {side} order for {quantity} {symbol}")
        return {
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "dry_run": True,
        }

    try:
        order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type='MARKET',
            quantity=quantity
        )
        logging.info(f"Placed {side} order for {quantity} {symbol}")
        return order
    except BinanceAPIException as e:
        logging.error(f"Error placing order {side} for {symbol}: {e}")
        return None

def trade_symbol(client, symbol):
    closes = get_klines(client, symbol)
    if closes is None:
        return

    sma_short = calculate_sma(closes, SMA_SHORT)
    sma_long = calculate_sma(closes, SMA_LONG)

    if sma_short is None or sma_long is None:
        logging.info(f"Not enough data to calculate SMA for {symbol}")
        return

    position = get_position(client, symbol)
    last_price = closes[-1]

    # Ensure leverage is set
    set_leverage(client, symbol, LEVERAGE)

    # Define trade amount: small fixed fraction of balance, e.g. 1% of USDT balance converted to qty
    try:
        balance_info = client.futures_account_balance()
        usdt_balance = float([b['balance'] for b in balance_info if b['asset'] == 'USDT'][0])
        trade_amount_usdt = usdt_balance * TRADE_BALANCE_FRACTION

        quantity = round(trade_amount_usdt / last_price, 3)  # round to 3 decimals

        # Trading logic:
        # If short SMA crosses above long SMA and no position or short position => go long
        # If short SMA crosses below long SMA and no position or long position => go short

        # We keep track only current position amount and try to flip it if signal changes

        if sma_short > sma_long and position <= 0:
            # Close short position if any, then open long
            if position < 0:
                logging.info(f"Closing short position on {symbol}")
                place_order(client, symbol, 'BUY', abs(position))

            logging.info(f"Going LONG on {symbol}")
            place_order(client, symbol, 'BUY', quantity)

        elif sma_short < sma_long and position >= 0:
            # Close long position if any, then open short
            if position > 0:
                logging.info(f"Closing long position on {symbol}")
                place_order(client, symbol, 'SELL', abs(position))

            logging.info(f"Going SHORT on {symbol}")
            place_order(client, symbol, 'SELL', quantity)

        else:
            logging.info(f"No trade signal for {symbol}")

    except Exception as e:
        logging.error(f"Error in trade_symbol for {symbol}: {e}")
