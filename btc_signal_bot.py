
import os
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = "https://api.binance.com/api/v3"
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
STATE_FILE = "paper_state.json"


def get_json(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "BTC-Paper-Signal-Bot"}
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode())


def telegram(message):
    if not TOKEN or not CHAT_ID:
        print("Telegram secrets not configured.")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID, "text": message
    }).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=15) as response:
        response.read()


def ema(values, period):
    alpha = 2 / (period + 1)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1 - alpha) * result
    return result


def rsi(values, period=14):
    changes = [values[i] - values[i - 1]
               for i in range(1, len(values))]
    gains = [max(x, 0) for x in changes[-period:]]
    losses = [max(-x, 0) for x in changes[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100 if avg_gain else 50
    return 100 - (100 / (1 + avg_gain / avg_loss))


def main():
    candles = get_json(
        f"{BASE}/klines?symbol=BTCUSDT&interval=15m&limit=100"
    )
    # Exclude the still-forming candle.
    closed = candles[:-1]
    closes = [float(c[4]) for c in closed]
    price = closes[-1]
    fast = ema(closes[-30:], 9)
    slow = ema(closes[-60:], 21)
    momentum = rsi(closes)

    if fast > slow and 52 <= momentum <= 68:
        signal = "WATCH UP"
    elif fast < slow and 32 <= momentum <= 48:
        signal = "WATCH DOWN"
    else:
        signal = "SKIP"

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    message = (
        f"BTC/USDT 15m PAPER SIGNAL\n"
        f"Decision: {signal}\n"
        f"Price: ${price:,.2f}\n"
        f"RSI: {momentum:.1f}\n"
        f"EMA 9: {fast:,.2f}\n"
        f"EMA 21: {slow:,.2f}\n"
        f"Checked: {timestamp}\n"
        f"Educational signal only; not a guaranteed trade."
    )
    print(message)
    telegram(message)


if __name__ == "__main__":
    main()
