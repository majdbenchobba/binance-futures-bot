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

## Notes

- default mode is testnet
- default mode is also `DRY_RUN=true`, so it will log the orders it would place without sending them
- set `RUN_ONCE=true` if you want a single scan/test cycle instead of a permanent loop
- sizing logic is intentionally simple
- if the old hardcoded keys were real, rotate them before publishing this repo
