"""make.fun BTC race bot: mean-reversion on confirmed recoveries at two horizons.

Reads the agent-fun/bars-replay/v1 hello, answers each batch with orders, one bar
at a time. Strategy: track closes, keep rolling highs/lows over a SHORT (~15 bar)
and a LONG (~60 bar) horizon. Buy only after a dip is confirmed by a recovery;
exit on take-profit, trailing stop, hard stop, or a stalled recovery. A risk
guard halts new buys when equity drawdown from peak exceeds a threshold, and a
warmup skips the first bars while indicators build history.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

# --- Tunable parameters -----------------------------------------------------
SHORT = 15          # short horizon (bars) for rolling high/low
LONG = 60           # long horizon (bars) for rolling high/low
D_SHORT = 60        # dip threshold (bps) below the short-horizon high
D_LONG = 120         # dip threshold (bps) below the long-horizon high
R = 20              # confirmation: recovery (bps) above the recent low
POSITION_FRAC = 50  # fraction of equity (percent) to spend per buy signal
TAKE_PROFIT = 100000    # exit: take profit (bps) above entry
TRAIL_STOP = 100     # exit: trailing stop (bps) below highest close since entry
HARD_STOP = 100      # exit: hard stop (bps) below entry
DRAWDOWN_HALT = 8   # risk guard: halt new buys if equity DD from peak exceeds %
WARMUP = 60         # warmup: no trades in the first WARMUP bars

BPS = 10000

class History:
    """Rolling window of closes plus the running high/low over a horizon."""

    __slots__ = ("closes", "horizon")

    def __init__(self, horizon):
        self.closes = []
        self.horizon = horizon

    def push(self, close):
        self.closes.append(close)
        if len(self.closes) > self.horizon:
            self.closes.pop(0)

    def ready(self):
        return len(self.closes) >= self.horizon

    def high(self):
        return max(self.closes)

    def low(self):
        return min(self.closes)


class Bot:
    """Per-symbol state: two rolling histories plus open-position bookkeeping."""

    def __init__(self):
        self.short = History(SHORT)
        self.long = History(LONG)
        self.peak_equity = None
        self.entry_price = None
        self.entry_low = None
        self.highest_since_entry = None
        self.prev_close = None
        self.higher_closes = 0
        self.bar_count = 0

_bots = {}


def on_batch(state, batch):
    """Answer one batch with the orders decided on this bar."""
    orders = []
    for bar in batch["bars"]:
        symbol = bar["symbol"]
        close = int(bar["c"])
        low = int(bar["l"])
        bot = _bots.get(symbol)
        if bot is None:
            bot = Bot()
            _bots[symbol] = bot
        orders = _decide(state, bot, symbol, close, low)
    return orders


def _decide(state, bot, symbol, close, low):
    """Compute the orders for one symbol on the current close."""
    bot.bar_count += 1
    orders = []

    # Risk guard: halt new buys if equity drawdown from peak exceeds threshold.
    if bot.peak_equity is None or state.equity > bot.peak_equity:
        bot.peak_equity = state.equity
    dd = (bot.peak_equity - state.equity) * 100 // bot.peak_equity if bot.peak_equity else 0
    halted = dd > DRAWDOWN_HALT

    held = state.positions.get(symbol)

    # Update rolling histories.
    bot.short.push(close)
    bot.long.push(close)

    # Track consecutive higher closes for the confirmation rule.
    if bot.prev_close is not None:
        if close > bot.prev_close:
            bot.higher_closes += 1
        else:
            bot.higher_closes = 0
    bot.prev_close = close

    # Exit logic for an open position.
    if held is not None:
        return _maybe_exit(state, bot, symbol, close, held)

    # Entry logic: only after warmup and when not halted.
    if bot.bar_count < WARMUP or halted:
        return []
    if not (bot.short.ready() and bot.long.ready()):
        return []
    return _maybe_enter(state, bot, symbol, close, low)


def _maybe_enter(state, bot, symbol, close, low):
    """Buy on a confirmed recovery after a dip at both horizons."""
    sh = bot.short.high()
    lh = bot.long.high()
    sl = bot.short.low()
    ll = bot.long.low()

    # DIP: close is at least D bps below the recent high at BOTH horizons.
    dip_short = (sh - close) * BPS // sh >= D_SHORT
    dip_long = (lh - close) * BPS // lh >= D_LONG
    if not (dip_short and dip_long):
        return []

    # CONFIRMATION: recovery above the recent low, or 2 consecutive higher closes.
    rec_short = (close - sl) * BPS // sl >= R
    rec_long = (close - ll) * BPS // ll >= R
    confirmed = (rec_short and rec_long) or bot.higher_closes >= 2
    if not confirmed:
        return []

    # Size: a fixed fraction of equity, capped by cash and the weight cap.
    spend = state.equity * POSITION_FRAC // 100
    if spend > state.cash:
        spend = state.cash
    if spend < int(state.hello["fees"]["min_notional_quote_units"]):
        return []
    bot.entry_price = close
    bot.entry_low = low
    bot.highest_since_entry = close
    return [{"side": "buy", "symbol": symbol, "notional_quote_units": spend, "max_slippage_bps": 100}]


def _maybe_exit(state, bot, symbol, close, held):
    """Sell the open position on take-profit, trailing stop, hard stop, or a stalled recovery."""
    entry = bot.entry_price
    if entry is None:
        bot.entry_price = close
        bot.entry_low = close
        bot.highest_since_entry = close
        return []

    # Track the highest close since entry.
    if bot.highest_since_entry is None or close > bot.highest_since_entry:
        bot.highest_since_entry = close

    # Take profit: close is at least TAKE_PROFIT bps above entry.
    if (close - entry) * BPS // entry >= TAKE_PROFIT:
        return _sell_all(state, symbol, held)

    # Hard stop: close is at least HARD_STOP bps below entry.
    if (entry - close) * BPS // entry >= HARD_STOP:
        return _sell_all(state, symbol, held)

    # Trailing stop: close falls TRAIL_STOP bps below the highest close since entry.
    if bot.highest_since_entry is not None:
        if (bot.highest_since_entry - close) * BPS // bot.highest_since_entry >= TRAIL_STOP:
            return _sell_all(state, symbol, held)

    return []


def _sell_all(state, symbol, held):
    """Sell the whole position."""
    return [{"side": "sell", "symbol": symbol, "qty": held.qty, "max_slippage_bps": 100}]


makefun_bars.run(on_batch)
