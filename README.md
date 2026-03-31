# Binance Futures SMA Bot

Small Binance Futures bot that scans volatile perpetual pairs and trades a basic SMA crossover.

It is set up for testnet use by default and now manages a fuller trade lifecycle than the first version:
- filter-aware market order sizing
- one-way mode guardrails
- optional symbol allowlist for faster testing
- automatic stop-loss and take-profit protection after entry via Binance conditional algo orders
- cleanup of stale protection orders when positions disappear

It is in a much better state for testnet verification, but it is still not something I would point at real money without more monitoring, reconciliation, and long-run burn-in.

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

## Protective order settings

These are the main lifecycle settings:

```env
STOP_LOSS_PCT=0.01
TAKE_PROFIT_PCT=0.02
PROTECTION_WORKING_TYPE=MARK_PRICE
PRICE_PROTECT=true
```

On a filled long, the bot places:
- one `STOP_MARKET` close-all order below entry
- one `TAKE_PROFIT_MARKET` close-all order above entry

On a filled short, it mirrors those levels above and below entry.

If a position exists but the matching protection orders are missing, the bot will recreate them on the next loop.

## Safe live testnet pass

If you want to test actual order placement on Binance Futures testnet, keep the size small and run one cycle:

```env
USE_TESTNET=true
DRY_RUN=false
RUN_ONCE=true
SYMBOL_ALLOWLIST=BTCUSDT
MAX_SYMBOL_SCAN=1
TRADE_BALANCE_FRACTION=0.005
STOP_LOSS_PCT=0.005
TAKE_PROFIT_PCT=0.01
```

That is still a testnet-only check. It is useful for verifying that entry, stop-loss, and take-profit orders all get accepted by Binance.

## Notes

- default mode is testnet
- default mode is also `DRY_RUN=true`, so it will log the orders it would place without sending them
- set `RUN_ONCE=true` if you want a single scan/test cycle instead of a permanent loop
- `SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT` is useful for fast dry-run testing
- `MAX_SYMBOL_SCAN` can limit how many perpetual symbols get scanned in one pass
- the bot now sizes market orders against Binance symbol filters instead of using a fixed decimal round
- protective orders use Binance close-all conditional algo orders so they can be restored after a restart
- it expects one-way mode unless you explicitly change that behavior
- if the old hardcoded keys were real, rotate them before publishing this repo
