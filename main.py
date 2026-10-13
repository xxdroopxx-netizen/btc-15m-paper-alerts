
import os
import csv
import json
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone

# ============================================================
# BTC 15-MINUTE PAPER TRADING TRACKER — VERSION 2
# Simulation only. This script never places live orders.
# ============================================================

VERSION = "PAPER TRACKER VERSION 2"

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

STATE_FILE = Path("paper_state.json")
TRADES_FILE = Path("paper_trades.csv")

STARTING_EQUITY = 1000.00
TRADE_NOTIONAL = 100.00
FEE_RATE = 0.001       # 0.10% per side
SLIPPAGE = 0.0005      # 0.05% simulated per side

FIELDS = [
    "entry_time",
    "exit_time",
    "entry_price",
    "exit_price",
    "quantity_btc",
    "gross_pnl",
    "fees",
    "net_pnl",
    "equity_after",
    "exit_signal",
]


def utc_time(timestamp):
    return datetime.fromtimestamp(
        int(timestamp), timezone.utc
    ).strftime("%Y-%m-%d %H:%M UTC")


def get_candles():
    """Fetch completed Coinbase BTC/USD 15-minute candles."""
    url = (
        "https://api.exchange.coinbase.com/"
        "products/BTC-USD/candles?granularity=900"
    )

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "BTC-15m-Paper-Tracker/2.0"},
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        raw = json.loads(response.read().decode())

    now = int(datetime.now(timezone.utc).timestamp())

    candles = sorted(
        [
            candle for candle in raw
            if int(candle[0]) + 900 <= now
        ],
        key=lambda candle: int(candle[0]),
    )

    if len(candles) < 22:
        raise RuntimeError(
            "Not enough completed 15-minute candles."
        )

    return candles


def send_telegram(message):
    """Send a Telegram message using repository secrets."""
    if not TOKEN or not CHAT_ID:
        raise RuntimeError(
            "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID secret."
        )

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": message,
    }).encode()

    request = urllib.request.Request(url, data=data)

    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.loads(response.read().decode())

    if not result.get("ok"):
        raise RuntimeError("Telegram rejected the message.")


def load_state():
    """Load saved state or create a fresh simulation."""
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text())

        required = {
            "last_candle",
            "position",
            "realized_pnl",
            "closed_trades",
            "wins",
            "peak_equity",
            "max_drawdown_pct",
        }

        if not required.issubset(state):
            raise RuntimeError(
                "Paper state file is incomplete. "
                "Back it up before repairing it."
            )

        return state

    return {
        "last_candle": None,
        "position": None,
        "realized_pnl": 0.0,
        "closed_trades": 0,
        "wins": 0,
        "peak_equity": STARTING_EQUITY,
        "max_drawdown_pct": 0.0,
    }


def save_state(state):
    """Persist state locally for the workflow to commit."""
    STATE_FILE.write_text(
        json.dumps(state, indent=2)
    )


def ensure_trade_log():
    if not TRADES_FILE.exists():
        with TRADES_FILE.open("w", newline="") as file:
            writer = csv.DictWriter(
                file, fieldnames=FIELDS
            )
            writer.writeheader()


def log_trade(record):
    with TRADES_FILE.open("a", newline="") as file:
        writer = csv.DictWriter(
            file, fieldnames=FIELDS
        )
        writer.writerow(record)


def get_signal(closes, i):
    """Calculate 9/21 moving-average crossover at candle i."""
    previous_fast = sum(closes[i - 9:i]) / 9
    fast = sum(closes[i - 8:i + 1]) / 9

    previous_slow = sum(closes[i - 21:i]) / 21
    slow = sum(closes[i - 20:i + 1]) / 21

    signal = "HOLD"

    if previous_fast <= previous_slow and fast > slow:
        signal = "BUY"
    elif previous_fast >= previous_slow and fast < slow:
        signal = "SELL"

    return signal, fast, slow


def process_candle(state, candles, closes, i):
    timestamp = int(candles[i][0])
    price = closes[i]

    signal, fast, slow = get_signal(closes, i)
    event = "No position change"

    # Open one simulated long position on a BUY crossover.
    if signal == "BUY" and state["position"] is None:
        entry_fill = price * (1 + SLIPPAGE)
        quantity = TRADE_NOTIONAL / entry_fill
        entry_fee = TRADE_NOTIONAL * FEE_RATE

        state["position"] = {
            "entry_time": utc_time(timestamp),
            "entry_price": entry_fill,
            "quantity_btc": quantity,
            "entry_fee": entry_fee,
        }

        event = (
            f"PAPER BUY opened near ${price:,.2f}; "
            f"simulated size ${TRADE_NOTIONAL:.2f}"
        )

    # Close the simulated long position on a SELL crossover.
    elif signal == "SELL" and state["position"] is not None:
        position = state["position"]

        exit_fill = price * (1 - SLIPPAGE)
        quantity = position["quantity_btc"]
        exit_value = quantity * exit_fill
        exit_fee = exit_value * FEE_RATE

        gross_pnl = (
            exit_fill - position["entry_price"]
        ) * quantity

        total_fees = position["entry_fee"] + exit_fee
        net_pnl = gross_pnl - total_fees

        state["realized_pnl"] += net_pnl
        state["closed_trades"] += 1

        if net_pnl > 0:
            state["wins"] += 1

        equity = STARTING_EQUITY + state["realized_pnl"]
        state["peak_equity"] = max(
            state["peak_equity"], equity
        )

        drawdown = (
            (state["peak_equity"] - equity)
            / state["peak_equity"] * 100
        )

        state["max_drawdown_pct"] = max(
            state["max_drawdown_pct"], drawdown
        )

        log_trade({
            "entry_time": position["entry_time"],
            "exit_time": utc_time(timestamp),
            "entry_price": round(
                position["entry_price"], 4
            ),
            "exit_price": round(exit_fill, 4),
            "quantity_btc": round(quantity, 8),
            "gross_pnl": round(gross_pnl, 4),
            "fees": round(total_fees, 4),
            "net_pnl": round(net_pnl, 4),
            "equity_after": round(equity, 2),
            "exit_signal": signal,
        })

        event = (
            f"PAPER SELL closed near ${price:,.2f}\n"
            f"Trade net P/L after simulated costs: "
            f"${net_pnl:+.2f}"
        )

        state["position"] = None

    state["last_candle"] = timestamp

    equity = STARTING_EQUITY + state["realized_pnl"]
    count = state["closed_trades"]
    wins = state["wins"]

    win_rate = wins / count * 100 if count else 0.0

    position_text = (
        "LONG OPEN"
        if state["position"] is not None
        else "FLAT"
    )

    message = (
        f"{VERSION}\n"
        f"BTC/USD 15m PAPER SIGNAL: {signal}\n"
        f"Closed candle: {utc_time(timestamp)}\n"
        f"Price: ${price:,.2f}\n"
        f"Fast MA (9): ${fast:,.2f}\n"
        f"Slow MA (21): ${slow:,.2f}\n"
        f"Event: {event}\n"
        f"Position: {position_text}\n"
        f"Closed trades: {count}\n"
        f"Win rate: {win_rate:.1f}%\n"
        f"Realized P/L: ${state['realized_pnl']:+.2f}\n"
        f"Virtual equity: ${equity:,.2f}\n"
        f"Max closed-equity drawdown: "
        f"{state['max_drawdown_pct']:.2f}%\n"
        "SIMULATION ONLY — NO LIVE ORDERS."
    )

    print(message)

    # Alert on actionable crossover signals, not every HOLD.
    if signal in ("BUY", "SELL"):
        send_telegram(message)
        print("SUCCESS: Telegram signal sent.")


def main():
    print(f"STARTING {VERSION}")
    print(f"Python file: {Path(__file__).name}")
    print("Mode: PAPER ONLY — NO LIVE ORDERS")

    if not TOKEN or not CHAT_ID:
        raise RuntimeError(
            "Telegram repository secrets are missing."
        )

    ensure_trade_log()

    candles = get_candles()
    closes = [float(candle[4]) for candle in candles]
    state = load_state()

    last_candle = state.get("last_candle")

    # First run establishes a baseline. It does not invent
    # trades from candles before tracking began.
    if last_candle is None:
        state["last_candle"] = int(candles[-1][0])
        save_state(state)

        message = (
            f"{VERSION}\n"
            "BTC PAPER TRACKER INITIALIZED\n"
            f"Baseline candle: {utc_time(candles[-1][0])}\n"
            f"Virtual starting equity: ${STARTING_EQUITY:.2f}\n"
            "Tracking begins at this baseline.\n"
            "No historical trades counted.\n"
            "No live orders."
        )

        send_telegram(message)
        print(message)
        print("STATE FILE CREATED: paper_state.json")
        print("TRADE LOG READY: paper_trades.csv")
        return

    # Only process candles newer than the saved timestamp.
    new_indices = [
        i for i, candle in enumerate(candles)
        if int(candle[0]) > int(last_candle)
    ]

    if not new_indices:
        print("No new completed candle; nothing to process.")
        print(f"Saved state exists: {STATE_FILE.exists()}")
        print(f"Trade log exists: {TRADES_FILE.exists()}")
        return

    for i in new_indices:
        if i < 21:
            state["last_candle"] = int(candles[i][0])
            save_state(state)
            continue

        process_candle(state, candles, closes, i)
        save_state(state)

    print("Paper state and trade log updated.")
    print(f"STATE FILE EXISTS: {STATE_FILE.exists()}")
    print(f"TRADE LOG EXISTS: {TRADES_FILE.exists()}")


if __name__ == "__main__":
    main()
