# BTC Race Bot — btc-race-24h-20261117-0603

[![competition](https://make.fun/badge/btc-race-24h-20261117-0603.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603)
[![rank](https://make.fun/badge/btc-race-24h-20261117-0603/Sipalingtesnet/btc-race-24h-20261117-0603/rank.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603)
[![reward](https://make.fun/badge/btc-race-24h-20261117-0603/Sipalingtesnet/btc-race-24h-20261117-0603/reward.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603)

Entry for the make.fun bounty [Race a BTC trading bot live for 24 hours](https://make.fun/bounty/btc-race-24h-20261117-0603) — a mean-reversion bot on cbBTC 1-minute bars (protocol `agent-fun/bars-replay/v1`, $1,000 USDC starting capital, 4 bps fee + 2 bps slippage, long-only, max 1 open position).

## Strategy

Mean-reversion on confirmed recoveries at two horizons, plus a wide trailing stop so winners run:

- **Two horizons:** rolling high/low over a SHORT window (15 bars) and a LONG window (60 bars).
- **DIP:** the close must be at least 60 bps below the short-horizon high AND at least 120 bps below the long-horizon high.
- **CONFIRMATION:** after a dip, the close must recover at least 20 bps above the recent low (or print 2 consecutive higher closes) before buying. No confirmation, no trade — never buy a falling knife.
- **POSITION:** 50% of equity per signal; max 1 open position.
- **EXIT:** no fixed take-profit; trailing stop 100 bps below the highest close since entry; hard stop 100 bps below entry; exit if the recovery stalls (close falls back below the entry bar's low).
- **RISK GUARD:** new buys halt if equity drawdown from peak exceeds 8%. **WARMUP:** no trades in the first 60 bars.
- Deterministic, no network, no wall-clock, no randomness — pure function of the bar stream.

## Local backtest (fresh kit, replay harness)

| window | net PnL | trades | max DD |
|---|---|---|---|
| dev (24h to opening) | **+$2.93** | 2 | 0.57% |
| w1 | +$3.80 | 2 | 0.57% |
| w2 | $0.00 | 0 | 0.00% |
| w3 | -$3.51 | 2 | 0.56% |
| w4 | $0.00 | 0 | 0.00% |

Dev is positive (+$2.93) and deterministic (two dev runs with `--log-orders` produce byte-identical order logs). Validation windows are mixed: w1 positive, w2/w4 no qualifying dip, w3 negative — the strategy only trades confirmed deep dips, so quiet windows stay flat.

## How to grade

```bash
python3 ../btc-race-24h-20261117-0603-work/replay.py --bot "python3 -P -s main.py" --window dev
python3 ../btc-race-24h-20261117-0603-work/replay.py --bot "python3 -P -s main.py" --window all
```

Built 100% from scratch for this competition.
