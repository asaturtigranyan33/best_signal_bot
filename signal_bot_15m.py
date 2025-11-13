#!/usr/bin/env python3
# multi_hammer_shooting_15m.py
# Scans multiple pairs on Binance every 15-minute candle boundary for Hammer / Shooting Star
# Sends Telegram notification when pattern found.

import ccxt
import pandas as pd
import time
import requests
from datetime import datetime, timezone

# === CONFIG: set your token/chat id here ===
BOT_TOKEN = ""
CHAT_ID = ""

PAIRS = ["ETH/USDT", "BCH/USDT", "SOL/USDT", "TON/USDT", "LINK/USDT"]
TIMEFRAME = "15m"
FETCH_LIMIT = 10
INTER_PAIR_DELAY = 1.0   # seconds between pair fetches to be gentle with API
LOGFILE = "signals.log"

exchange = ccxt.binance({"enableRateLimit": True})

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            print("Telegram send failed:", r.status_code, r.text)
    except Exception as e:
        print("Telegram error:", e)

def log_signal(text):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {text}\n")

def fetch_ohlcv_df(symbol, timeframe=TIMEFRAME, limit=FETCH_LIMIT):
    data = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(data, columns=["ts","open","high","low","close","volume"])
    df["time"] = pd.to_datetime(df["ts"], unit="ms")
    df.set_index("time", inplace=True)
    df = df.astype(float)
    return df

# pattern definitions (same logic as before)
def is_hammer_candle(c):
    o, h, l, cl = c['open'], c['high'], c['low'], c['close']
    body = abs(cl - o)
    if body == 0:
        return False
    lower = min(o, cl) - l
    upper = h - max(o, cl)
    return (lower > body * 1.8) and (upper < body * 0.6)

def is_shooting_star_candle(c):
    o, h, l, cl = c['open'], c['high'], c['low'], c['close']
    body = abs(cl - o)
    if body == 0:
        return False
    upper = h - max(o, cl)
    lower = min(o, cl) - l
    return (upper > body * 1.8) and (lower < body * 0.6)

def analyze_pair(pair):
    try:
        df = fetch_ohlcv_df(pair)
    except Exception as e:
        print(f"[{pair}] fetch error: {e}")
        return []

    # մենք հիմա վերլուծում ենք նախորդ մոմը (փակված մոմը)
    last_closed = df.iloc[-2]
    candle = {
        "open": last_closed["open"],
        "high": last_closed["high"],
        "low": last_closed["low"],
        "close": last_closed["close"]
    }

    signals = []
    if is_hammer_candle(candle):
        price = last_closed["close"]
        signals.append(("HAMMER", "LONG", price))
    elif is_shooting_star_candle(candle):
        price = last_closed["close"]
        signals.append(("SHOOTING_STAR", "SHORT", price))

    return signals

def seconds_until_next_15min():
    """Return seconds until next 15-minute candle boundary (UTC aligned)."""
    now = int(time.time())
    # number of seconds since epoch modulo 900 (15*60)
    rem = now % (15 * 60)
    if rem == 0:
        return 0
    return (15 * 60) - rem

def main():
    print("Starting Hammer/Shooting 15m scanner for:", ", ".join(PAIRS))
    # Align to candle boundary: if we started between candles, wait until next candle close
    wait0 = seconds_until_next_15min()
    if wait0:
        print(f"Aligning to 15m boundary: sleeping {wait0} seconds...")
        time.sleep(wait0 + 1)  # wait until first full candle closes (+1s safety)

    while True:
        cycle_start = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"[{cycle_start}] Scanning pairs...")
        any_signal = False

        for pair in PAIRS:
            try:
                signals = analyze_pair(pair)
                if signals:
                    any_signal = True
                    for typ, direction, price in signals:
                        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                        if typ == "HAMMER":
                            msg = f"🟢 <b>Hammer detected</b>\nPair: {pair}\nDirection: LONG\nPrice: {price}\nTF: {TIMEFRAME}\nTime: {ts}"
                        else:
                            msg = f"🔴 <b>Shooting Star detected</b>\nPair: {pair}\nDirection: SHORT\nPrice: {price}\nTF: {TIMEFRAME}\nTime: {ts}"
                        print(f"[{pair}] SIGNAL -> {typ} @ {price}")
                        send_telegram(msg)
                        log_signal(f"{pair} | {typ} | {direction} | price={price} | time={ts}")
                else:
                    print(f"[{pair}] No pattern.")
            except Exception as e:
                print(f"[{pair}] analyze error: {e}")
            time.sleep(INTER_PAIR_DELAY)

        # after scanning current candle, sleep until next 15m candle closes
        to_sleep = seconds_until_next_15min()
        # if 0, it means we're exactly on boundary; sleep full 15m
        if to_sleep == 0:
            to_sleep = 15 * 60
        print(f"Cycle complete. Sleeping {to_sleep} seconds until next 15m candle...")
        time.sleep(to_sleep + 1)  # +1s safety to ensure new candle exists

if __name__ == "__main__":
    main()
