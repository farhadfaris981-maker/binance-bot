# -*- coding: utf-8 -*-
import os
import time
import threading
import numpy as np
import requests
from flask import Flask
from binance.client import Client
from binance.enums import *

# ==================== قراءة الإعدادات ====================
BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY")
BINANCE_API_SECRET = os.environ.get("BINANCE_API_SECRET")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
PROXY_HOST = os.environ.get("PROXY_HOST")
PROXY_PORT = os.environ.get("PROXY_PORT")
PROXY_PROTOCOL = os.environ.get("PROXY_PROTOCOL", "socks5")

SYMBOL = "BTCUSDT"
INTERVAL = Client.KLINE_INTERVAL_5MINUTE
QUANTITY = 0.001
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
BB_PERIOD = 20
BB_STD = 2
TP_PERCENT = 1.02
SL_PERCENT = 0.98

PROXY_URL = f"{PROXY_PROTOCOL}://{PROXY_HOST}:{PROXY_PORT}" if PROXY_HOST else None

# ==================== Flask App ====================
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Binance Bot is running!"

# ==================== الاتصال ====================
client = None
try:
    requests_params = {}
    if PROXY_URL:
        requests_params["proxies"] = {"http": PROXY_URL, "https": PROXY_URL}
    client = Client(
        BINANCE_API_KEY,
        BINANCE_API_SECRET,
        testnet=True,
        requests_params=requests_params
    )
    print("✅ تم الاتصال بـ Binance Spot Testnet")
except Exception as e:
    print(f"❌ فشل الاتصال: {e}")

# ==================== الدوال ====================
def get_balance():
    try:
        account = client.get_account()
        btc = 0.0
        usdt = 0.0
        for b in account['balances']:
            if b['asset'] == 'BTC':
                btc = float(b['free'])
            if b['asset'] == 'USDT':
                usdt = float(b['free'])
        return btc, usdt
    except Exception as e:
        print(f"⚠️ خطأ في جلب الرصيد: {e}")
        return None, None

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=10)
    except Exception as e:
        print(f"⚠️ فشل إرسال Telegram: {e}")

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    deltas = np.diff(closes)
    seed = deltas[:period]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    if down == 0:
        return 100.0
    rs = up / down
    return 100 - (100 / (1 + rs))

def calc_bollinger(closes, period=20, std_mult=2):
    if len(closes) < period:
        return None, None, None
    sma = np.mean(closes[-period:])
    stdev = np.std(closes[-period:])
    return sma + (std_mult * stdev), sma, sma - (std_mult * stdev)

def get_klines():
    klines = client.get_klines(symbol=SYMBOL, interval=INTERVAL, limit=100)
    return [float(k[4]) for k in klines]

def place_order(side):
    try:
        return client.create_order(
            symbol=SYMBOL,
            side=side,
            type=ORDER_TYPE_MARKET,
            quantity=QUANTITY,
        )
    except Exception as e:
        print(f"⚠️ خطأ في الأمر: {e}")
        return None

# ==================== حلقة البوت ====================
def bot_loop():
    if client is None:
        print("❌ لا يمكن تشغيل البوت بدون اتصال.")
        return
    print("🚀 تشغيل البوت...")
    send_telegram("🚀 تم تشغيل البوت على Binance Spot Testnet")
    btc, usdt = get_balance()
    if btc is not None:
        send_telegram(f"💰 الرصيد الأولي:\nBTC: {btc:.6f}\nUSDT: {usdt:.2f}")

    in_position = False
    entry_price = 0

    while True:
        try:
            closes = get_klines()
            rsi = calc_rsi(closes, RSI_PERIOD)
            upper, mid, lower = calc_bollinger(closes, BB_PERIOD, BB_STD)
            price = closes[-1]
            btc, usdt = get_balance()

            signal = "HOLD"
            if rsi < RSI_OVERSOLD and price <= lower:
                signal = "BUY"
            elif rsi > RSI_OVERBOUGHT and price >= upper:
                signal = "SELL"

            print(f"💰 {price:.2f} | RSI: {rsi:.2f} | {signal}")
            if btc is not None:
                print(f"   💼 BTC: {btc:.6f} | USDT: {usdt:.2f}")

            if signal == "BUY" and not in_position:
                if place_order(SIDE_BUY):
                    entry_price = price
                    in_position = True
                    send_telegram(f"🟢 شراء!\n💰 {entry_price:.2f}\n🛑 SL: {entry_price*SL_PERCENT:.2f}\n✅ TP: {entry_price*TP_PERCENT:.2f}")

            elif in_position:
                if price >= entry_price * TP_PERCENT:
                    place_order(SIDE_SELL)
                    send_telegram(f"✅ جني الأرباح عند {price:.2f}")
                    in_position = False
                elif price <= entry_price * SL_PERCENT:
                    place_order(SIDE_SELL)
                    send_telegram(f"🛑 وقف الخسارة عند {price:.2f}")
                    in_position = False

        except Exception as e:
            print(f"⚠️ خطأ: {e}")

        time.sleep(300)

# ==================== التشغيل ====================
if __name__ == "__main__":
    # تشغيل البوت في Thread منفصل
    bot_thread = threading.Thread(target=bot_loop, daemon=True)
    bot_thread.start()
    # تشغيل Flask للرد على Ping
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
