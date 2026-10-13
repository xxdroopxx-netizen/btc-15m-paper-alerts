 
import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

def get_candles():
    url = "https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=900"
    request = urllib.request.Request(
        url, headers={"User-Agent": "BTC-Paper-Signals/1.0"}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        candles = json.loads(response.read().decode())

    now = int(datetime.now(timezone.utc).timestamp())
    completed = sorted(
        [c for c in candles if int(c[0]) + 900 <= now],
        key=lambda c: int(c[0])
    )

    if len(completed) < 22:
        raise RuntimeError("Not enough completed 15-minute candles.")

    return completed

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": message
    }).encode()
    request = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.loads(response.read().decode())
    if not result.get("ok"):
        raise RuntimeError("Telegram rejected the message.")

def main():
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("Telegram secrets are missing.")

    candles = get_candles()
    closes = [float(c[4]) for c in candles]

    fast = sum(closes[-9:]) / 9
    slow = sum(closes[-21:]) / 21
    previous_fast = sum(closes[-10:-1]) / 9
    previous_slow = sum(closes[-22:-1]) / 21
    price = closes[-1]

    signal = "HOLD"
    if previous_fast <= previous_slow and fast > slow:
        signal = "BUY"
    elif previous_fast >= previous_slow and fast < slow:
        signal = "SELL"

    candle_time = datetime.fromtimestamp(
        int(candles[-1][0]), timezone.utc
    ).strftime("%Y-%m-%d %H:%M UTC")

    message = (
        f"BTC/USD 15-MIN PAPER SIGNAL: {signal}\n"
        f"Price: ${price:,.2f}\n"
        f"Fast MA (9): ${fast:,.2f}\n"
        f"Slow MA (21): ${slow:,.2f}\n"
        f"Completed candle: {candle_time}\n"
        "Paper mode only — no live trades."
    )

    print(message)
    send_telegram(message)
    print("SUCCESS: Telegram alert sent.")

if __name__ == "__main__":
    main()
