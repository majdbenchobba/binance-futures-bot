# Binance Futures SMA Bot

Small Binance Futures bot that scans volatile perpetual pairs and trades a basic SMA crossover.

It is set up for testnet use by default and now manages a fuller trade lifecycle than the first version:
- filter-aware market order sizing
- one-way mode guardrails
- optional symbol allowlist for faster testing
- automatic stop-loss and take-profit protection after entry via Binance conditional algo orders
- cleanup of stale protection orders when positions disappear
- operator guardrails for cooldowns, daily loss limits, and a manual kill switch
- optional webhook alerts plus continued management of open positions outside the top-volatility scan
- cycle-by-cycle account snapshots with position and unrealized PnL reporting

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

## Operator safety settings

These controls are aimed at keeping the bot from blindly stacking trades:

```env
MAX_OPEN_POSITIONS=1
SYMBOL_COOLDOWN_MINUTES=30
MAX_DAILY_LOSS_PCT=0.03
STATE_FILE=runtime/state.json
KILL_SWITCH_FILE=runtime/KILL_SWITCH
ALERT_BELL=false
ALERT_WEBHOOK_URL=
ALERT_TIMEOUT_SECONDS=5
REPORT_EVERY_CYCLES=1
ALERT_ON_POSITION_CHANGES=true
```

What they do:
- `MAX_OPEN_POSITIONS` limits how many non-flat symbols the bot can hold at once
- `SYMBOL_COOLDOWN_MINUTES` blocks a fresh re-entry on the same symbol for a while after a live fill
- `MAX_DAILY_LOSS_PCT` stops the bot if the wallet balance falls below the configured day-start threshold
- `KILL_SWITCH_FILE` lets you stop the bot manually by creating that file
- `STATE_FILE` stores the day-start balance and recent trade timestamps locally
- `ALERT_WEBHOOK_URL` can receive JSON alerts for halts, live entries, and errors
- `REPORT_EVERY_CYCLES` controls how often the bot logs a full account snapshot
- `ALERT_ON_POSITION_CHANGES` sends a webhook when the live position state changes

To stop the bot manually, create the kill-switch file:

```powershell
New-Item -ItemType Directory -Force -Path runtime | Out-Null
New-Item -ItemType File -Force -Path runtime\KILL_SWITCH | Out-Null
```

Delete that file when you want to allow trading again.

## Alert payloads

If you set `ALERT_WEBHOOK_URL`, the bot will send JSON like this:

```json
{
  "source": "binance-futures-bot",
  "level": "warning",
  "message": "Manual kill switch detected ...",
  "context": {
    "event": "guardrail_halt"
  },
  "dry_run": true,
  "testnet": true
}
```

That keeps the alerting generic, so you can forward it to your own endpoint, Discord bridge, Slack bridge, or any small notifier you control.

## Runtime Reporting

At the end of each cycle, the bot can log an account summary like:

```text
Cycle 12: wallet=4999.93 available=4975.10 uPnL=1.24 open_positions=1 protection_orders=2
ETHUSDT SHORT qty=0.011000 entry=2097.2100 mark=2089.5500 uPnL=0.0839 lev=5x protections=2 liq=2487.8300
```

That gives you a quick read on:
- wallet balance
- available balance
- total unrealized PnL
- open position count
- protection order count

When `ALERT_ON_POSITION_CHANGES=true`, the bot also sends a webhook when the structural position state changes, such as:
- flat -> open position
- open position -> flat
- protection count changes around an active position

## Coverage Outside The Scan List

The bot still uses the top-volatility scan to decide where new entries are allowed.

It also keeps managing symbols that are already active:
- open positions are still processed even if they fall out of the volatility shortlist
- symbols with leftover protection orders are reconciled so stale orders do not get ignored
- symbols outside the scan do not open fresh positions from flat

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
- runtime state is intentionally local-only and ignored by git
- alerts are optional; failed webhook delivery is logged but will not crash the bot
- it expects one-way mode unless you explicitly change that behavior
- if the old hardcoded keys were real, rotate them before publishing this repo
