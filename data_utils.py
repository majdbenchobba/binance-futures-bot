import logging
import numpy as np
from binance.client import Client
import requests
from config import MAX_SYMBOL_SCAN, SYMBOL_ALLOWLIST

def get_all_symbols(client):
    info = client.futures_exchange_info()
    # Filter for perpetual futures only
    symbols = [s['symbol'] for s in info['symbols'] if s['contractType'] == 'PERPETUAL']

    if SYMBOL_ALLOWLIST:
        symbols = [symbol for symbol in symbols if symbol in SYMBOL_ALLOWLIST]

    if MAX_SYMBOL_SCAN > 0:
        symbols = symbols[:MAX_SYMBOL_SCAN]

    return symbols

def get_volatility(client, symbol, interval='1h', lookback=24):
    try:
        logging.info(f"Fetching klines for {symbol}")
        klines = client.futures_klines(symbol=symbol, interval=interval, limit=lookback, timeout=5)  # timeout added
        if not klines:
            logging.warning(f"No klines data for {symbol}")
            return 0
        closes = np.array([float(k[4]) for k in klines])
        returns = np.diff(np.log(closes))
        volatility = np.std(returns) * np.sqrt(len(returns))
        return volatility
    except requests.exceptions.Timeout:
        logging.warning(f"Timeout fetching klines for {symbol}")
        return 0
    except Exception as e:
        logging.error(f"Error getting volatility for {symbol}: {e}")
        return 0

def get_top_volatile_symbols(client, top_n=3, interval='1h', lookback=24):
    symbols = get_all_symbols(client)
    vol_dict = {}
    for s in symbols:
        vol = get_volatility(client, s, interval, lookback)
        vol_dict[s] = vol
    sorted_syms = sorted(vol_dict.items(), key=lambda x: x[1], reverse=True)
    return [sym for sym, vol in sorted_syms[:top_n]]
