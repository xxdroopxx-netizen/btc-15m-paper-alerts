
import os
import json
import
 urllib.parse
import urllib.request
from pathlib import Path

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
STATE_FILE = Path("paper_state.json")


def get_json(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "BTC-Paper-Bot/1.0"}
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read())


def send_telegram(message):
    url = (
        f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    
    payload = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": message
    }).encode()
    req = urllib.request.Request(url, data=payload)
    with urllib.request.urlopen(req, timeout=20) as response:
        result = json.loads(response.read())
        if not result.get("ok"):
            raise RuntimeError("Telegram message failed")


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"position": None, "last_candle": None}


def main():
    # Public market data only. No exchange trading credentials.
    url = (
        https://api1.binance.com/api/v3/klines?
        symbol=BTCUSDT&interval=15m&limit=60
    )
    candles = get_json(url)

    # Use only completed candles, not the currently forming candle.
    candles = candles[:-1]
    closes = [float(c[4]) for c in candles]
    candle_time = candles[-1][0]

    fast = sum(closes[-9:]) / 9
    slow = sum(closes[-21:]) / 21
    previous_fast = sum(closes[-10:-1]) / 9
    previous_slow = sum(closes[-22:-1]) / 21
    price = closes[-1]

    state = load_state()

    if state.get("last_candle") == candle_time:
        print("This candle was already processed.")
        return

    signal = "HOLD"
    if previous_fast <= previous_slow and fast > slow:
        signal = "BUY"
    elif previous_fast >= previous_slow and fast < slow:
        signal = "SELL"

    message = (
        f"BTC/USDT 15m PAPER SIGNAL: {signal}\n"
        f"Price: ${price:,.2f}\n"
        f"Fast MA(9): {fast:,.2f}\n"
        f"Slow MA(21): {slow:,.2f}\n"
        "Simulated only — no live orders."
    )

    print(message)
    send_telegram(message)

    # This starter logs signals, not real orders or verified profits.
    state["last_candle"] = candle_time
    state["last_signal"] = signal
    STATE_FILE.write_text(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()m
