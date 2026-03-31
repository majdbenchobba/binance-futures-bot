import numpy as np
from binance.client import Client
import time

API_KEY = ''     # put your Binance API key here or leave empty for public data
API_SECRET = ''  # put your Binance secret here or leave empty for public data

# Parameters
FAST_SMA = 10
SLOW_SMA = 50
FEE_RATE = 0.0004  # 0.04% per trade assumed fees
LOOKBACK = 500     # number of klines to fetch
INTERVAL = '1h'    # Kline interval

# List of symbols to backtest - add/remove as you want
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'ADAUSDT']

def get_klines(client, symbol, interval, limit):
    print(f"Fetching klines for {symbol}...")
    klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    closes = np.array([float(k[4]) for k in klines])
    return closes

def calculate_sma(data, period):
    return np.convolve(data, np.ones(period)/period, mode='valid')

def backtest_sma_crossover(closes, fast_period, slow_period, fee_rate):
    trades = []
    # Calculate SMAs
    sma_fast = calculate_sma(closes, fast_period)
    sma_slow = calculate_sma(closes, slow_period)

    # Because SMA arrays are shorter than closes, align index
    offset = slow_period - fast_period
    sma_fast = sma_fast[offset:] if offset > 0 else sma_fast
    sma_slow = sma_slow[:len(sma_fast)]

    position = None  # None, 'long'
    entry_price = 0
    entry_index = 0

    for i in range(1, len(sma_fast)):
        # SMA crossover logic
        if position is None:
            # Look for buy signal
            if sma_fast[i-1] < sma_slow[i-1] and sma_fast[i] > sma_slow[i]:
                # Buy at close price aligned with SMA start
                entry_price = closes[i + slow_period - 1]
                entry_index = i + slow_period - 1
                position = 'long'
                trades.append({'type':'buy', 'price': entry_price, 'index': entry_index})
                print(f"BUY at {entry_price:.4f} on index {entry_index}")
        else:
            # Look for sell signal
            if sma_fast[i-1] > sma_slow[i-1] and sma_fast[i] < sma_slow[i]:
                exit_price = closes[i + slow_period - 1]
                exit_index = i + slow_period - 1
                gross_profit = exit_price - entry_price
                fees = (entry_price + exit_price) * fee_rate
                net_profit = gross_profit - fees
                pct_return = net_profit / entry_price * 100
                trades.append({'type':'sell', 'price': exit_price, 'index': exit_index, 'profit': net_profit})
                print(f"SELL at {exit_price:.4f} on index {exit_index} | Profit: {net_profit:.4f} ({pct_return:.2f}%)")
                position = None

    # Close any open position at last price (forced close)
    if position == 'long':
        exit_price = closes[-1]
        exit_index = len(closes) - 1
        gross_profit = exit_price - entry_price
        fees = (entry_price + exit_price) * fee_rate
        net_profit = gross_profit - fees
        pct_return = net_profit / entry_price * 100
        trades.append({'type':'sell', 'price': exit_price, 'index': exit_index, 'profit': net_profit})
        print(f"SELL at {exit_price:.4f} on index {exit_index} | Profit: {net_profit:.4f} ({pct_return:.2f}%) (forced close)")

    return trades

def summarize_trades(trades):
    total_trades = len([t for t in trades if t['type']=='sell'])
    wins = len([t for t in trades if t.get('profit', 0) > 0])
    losses = total_trades - wins
    total_profit = sum(t.get('profit', 0) for t in trades if t['type']=='sell')
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

    print("\n=== Backtest Summary ===")
    print(f"Total Trades: {total_trades}")
    print(f"Wins: {wins}")
    print(f"Losses: {losses}")
    print(f"Win Rate: {win_rate:.2f}%")
    print(f"Total Profit: {total_profit:.4f} (price units)")
    print("=======================")

def main():
    client = Client(API_KEY, API_SECRET)

    for symbol in SYMBOLS:
        try:
            closes = get_klines(client, symbol, INTERVAL, LOOKBACK)
            print(f"Starting backtest for {symbol} with fast SMA={FAST_SMA}, slow SMA={SLOW_SMA}")
            trades = backtest_sma_crossover(closes, FAST_SMA, SLOW_SMA, FEE_RATE)
            summarize_trades(trades)
            print("\n" + "="*50 + "\n")
            time.sleep(1)  # avoid API rate limits
        except Exception as e:
            print(f"Error backtesting {symbol}: {e}")

if __name__ == "__main__":
    main()
