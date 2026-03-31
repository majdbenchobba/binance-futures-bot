# Binance Futures SMA Bot

Small Binance Futures bot that scans volatile perpetual pairs and trades a basic SMA crossover.

It is set up for testnet use by default. I would treat it as an experiment repo, not a production trading system.

## Install

```bash
pip install -r requirements.txt
```

## Setup

Copy `.env.example` to `.env`, then add your Binance testnet keys.

## Run

Bot:

```bash
python bot.py
```

Backtest:

```bash
python backtest.py
```

The backtest only uses public market data, so it does not need keys.

## Testnet dry-run check

If you want a safe test pass:

```env
USE_TESTNET=true
DRY_RUN=true
RUN_ONCE=true
SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT
MAX_SYMBOL_SCAN=3
```

That runs one scan cycle, computes signals, and logs the orders it would place without actually sending them.

## Notes

- default mode is testnet
- default mode is also `DRY_RUN=true`, so it will log the orders it would place without sending them
- set `RUN_ONCE=true` if you want a single scan/test cycle instead of a permanent loop
- `SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT` is useful for fast dry-run testing
- `MAX_SYMBOL_SCAN` can limit how many perpetual symbols get scanned in one pass
- the bot now sizes market orders against Binance symbol filters instead of using a fixed decimal round
- it expects one-way mode unless you explicitly change that behavior
- if the old hardcoded keys were real, rotate them before publishing this repo
