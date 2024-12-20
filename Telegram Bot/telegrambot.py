import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from ta.trend import EMAIndicator
import json
import mplfinance as mp
import pandas as pd
import numpy as np
import ta
import os
import sys
import threading
import time
import mplfinance as mpf
import feedparser
import matplotlib.pyplot as plt
from io import BytesIO
import random
import hmac
import hashlib
from datetime import datetime, timedelta
from ta.trend import PSARIndicator

# API Anahtarları
BINANCE_DEPOSIT_URL = "https://api.binance.com/api/v3/deposit"
BINANCE_API_URL = "https://api.binance.com/api/v3/ticker/24hr"
BINANCE_KLINE_URL = "https://api.binance.com/api/v3/klines"
TELEGRAM_BOT_TOKEN = "7817204061:AAGjfhYdPm-bX3pQZyGqs4wBMdHyMsRKKzk"

# CoinGecko API URL'si
COINGECKO_MARKET_URL = "https://api.coingecko.com/api/v3/global"
COINGECKO_COIN_INFO_URL = "https://api.coingecko.com/api/v3/coins/"

# Telegram botu
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

API_KEY = 'yoKhAZRwNGfJI45pL4t8SMCepYExce86fW3CdcleG5jLNf2njVb0OMtzRJ76ZDTB'
API_SECRET = 'zTqnqIizDtBTazefMZ1CB3UiSyqxujrTw0hqzCMIIWQFltQQMHyO8PrKF6MZOGTz'
BINANCE_DEPOSIT_URL = 'https://api.binance.com/sapi/v1/capital/deposit/hisrec'

# Zaman damgası oluştur
timestamp = int(time.time() * 1000)

# Sorgu stringi ve imza oluştur
query_string = f'timestamp={timestamp}'
signature = hmac.new(API_SECRET.encode(), query_string.encode(), hashlib.sha256).hexdigest()

headers = {
    'X-MBX-APIKEY': API_KEY
}

# API isteği yap
response = requests.get(f'{BINANCE_DEPOSIT_URL}?{query_string}&signature={signature}', headers=headers)

# Yanıtı ekrana yazdır
print(f"HTTP Status Code: {response.status_code}")
print(f"Response Text: {response.text}")


# Trend Takip ve SAR stratejisini hesaplayan fonksiyon
def calculate_trend_sar_signals(symbol, interval):
    kline_data = get_kline_data(symbol, interval)

    if not kline_data:
        return f"❌ {symbol} için {interval} verisi alınamadı."

    # Veriyi DataFrame'e dönüştür
    df = pd.DataFrame(kline_data, columns=["timestamp", "open", "high", "low", "close", "volume", "close_time", "quote_asset_volume", "number_of_trades", "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"])
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)

    # EMA 50 ile trend belirle
    df["EMA_50"] = EMAIndicator(df["close"], window=50).ema_indicator()

    # Parabolic SAR hesapla
    psar = PSARIndicator(high=df["high"], low=df["low"], close=df["close"])
    df["PSAR"] = psar.psar()

    # Trend belirleme
    if df["close"].iloc[-1] > df["EMA_50"].iloc[-1]:
        trend = "🟢 Yeşil Trend (Yükseliş)"
    elif df["close"].iloc[-1] < df["EMA_50"].iloc[-1]:
        trend = "🔴 Kırmızı Trend (Düşüş)"
    else:
        trend = "🟡 Sarı Trend (Kararsız)"

    # SAR sinyalleri
    sar_signal = ""
    if trend == "🟢 Yeşil Trend (Yükseliş)" and df["PSAR"].iloc[-1] < df["close"].iloc[-1]:
        sar_signal = "✅ *Al Sinyali*: SAR fiyatın altında."
    elif trend == "🔴 Kırmızı Trend (Düşüş)" and df["PSAR"].iloc[-1] > df["close"].iloc[-1]:
        sar_signal = "❌ *Sat Sinyali*: SAR fiyatın üstünde."
    else:
        sar_signal = "⚪ *Nötr Sinyal*: Belirgin bir sinyal yok."

    message_text = (
        f"📊 *{symbol} {interval} TREND TAKİP ve SAR Analizi:*\n\n"
        f"{trend}\n"
        f"{sar_signal}"
    )

    return message_text

# Telegram komutu ile strateji analizi yapan fonksiyon
@bot.message_handler(commands=['trend_sar'])
def send_trend_sar_strategy(message):
    try:
        args = message.text.split()
        if len(args) != 3:
            bot.send_message(message.chat.id, "Kullanım: /trend_sar [COIN] [ZAMAN_DILIMI] (Örn: /trend_sar BTC 1h)")
            return

        symbol = args[1].upper()
        interval = args[2]
        trend_sar_signal = calculate_trend_sar_signals(symbol, interval)
        bot.send_message(message.chat.id, trend_sar_signal, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Bir hata oluştu: {e}")



# Arz ve talep bölgelerini tespit eden fonksiyon
def detect_supply_demand_zones(df):
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)

    supply_zones = df[df['high'] == df['high'].rolling(5, center=True).max()]['high']
    demand_zones = df[df['low'] == df['low'].rolling(5, center=True).min()]['low']
    
    return supply_zones, demand_zones

# Hareketli ortalama kesişimlerini kontrol eden fonksiyon
def check_ema_crossover(df):
    ema_21 = EMAIndicator(df['close'], window=21).ema_indicator()
    ema_50 = EMAIndicator(df['close'], window=50).ema_indicator()

    if ema_21.iloc[-1] > ema_50.iloc[-1] and ema_21.iloc[-2] <= ema_50.iloc[-2]:
        return "🟢 Alım Sinyali: EMA 21, EMA 50'yi yukarı kesti."
    elif ema_21.iloc[-1] < ema_50.iloc[-1] and ema_21.iloc[-2] >= ema_50.iloc[-2]:
        return "🔴 Satım Sinyali: EMA 21, EMA 50'yi aşağı kesti."
    return "⚪ Kesişim Sinyali Yok."

# Telegram komutu ile analiz yapan fonksiyon
@bot.message_handler(commands=['stratejis'])
def send_strategy(message):
    try:
        args = message.text.split()
        if len(args) != 3:
            bot.send_message(message.chat.id, "Kullanım: /stratejis [COIN] [ZAMAN_DILIMI] (Örn: /strateji BTC 1h)")
            return

        symbol = args[1].upper()
        interval = args[2]
        kline_data = get_kline_data(symbol, interval)

        if not kline_data:
            bot.send_message(message.chat.id, f"❌ {symbol} için {interval} verisi alınamadı.")
            return

        # Veriyi DataFrame'e dönüştür
        df = pd.DataFrame(kline_data, columns=["timestamp", "open", "high", "low", "close", "volume", "close_time", "quote_asset_volume", "number_of_trades", "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"])
        df["close"] = df["close"].astype(float)

        # Arz ve Talep Bölgeleri
        supply_zones, demand_zones = detect_supply_demand_zones(df)

        # EMA Kesişim Sinyali
        ema_signal = check_ema_crossover(df)

        # Mesajı Oluştur
        message_text = (
            f"📊 *{symbol} {interval} Strateji Analizi:*\n\n"
            f"🔼 *Arz Bölgeleri*: {', '.join(supply_zones.astype(str).tolist())}\n"
            f"🔽 *Talep Bölgeleri*: {', '.join(demand_zones.astype(str).tolist())}\n\n"
            f"{ema_signal}"
        )

        bot.send_message(message.chat.id, message_text, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Bir hata oluştu: {e}")

# Giriş, stop-loss ve take-profit hesaplama fonksiyonu
def calculate_trade_levels(symbol, interval):
    kline_data = get_kline_data(symbol, interval)

    if not kline_data:
        return f"❌ {symbol} için {interval} verisi alınamadı."

    # Veriyi DataFrame'e dönüştür
    df = pd.DataFrame(kline_data, columns=["timestamp", "open", "high", "low", "close", "volume", "close_time", "quote_asset_volume", "number_of_trades", "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"])
    df["close"] = df["close"].astype(float)
    
    # EMA 21 hesapla
    df["EMA_21"] = EMAIndicator(df["close"], window=21).ema_indicator()

    # En son fiyat ve EMA 21 değeri
    latest_close = df["close"].iloc[-1]
    latest_ema21 = df["EMA_21"].iloc[-1]

    # Giriş ve stop seviyesi hesaplama
    stop_loss_percent = 2  # %2 stop-loss
    tp1_percent = 2        # %2 TP1
    tp2_percent = 4        # %4 TP2
    tp3_percent = 6        # %6 TP3

    if latest_close > latest_ema21:
        entry_price = latest_close
        stop_loss = entry_price * (1 - stop_loss_percent / 100)
        tp1 = entry_price * (1 + tp1_percent / 100)
        tp2 = entry_price * (1 + tp2_percent / 100)
        tp3 = entry_price * (1 + tp3_percent / 100)

        signal = (
            f"🟢 *Alım Sinyali*: {symbol} {interval}\n\n"
            f"💰 *Giriş Fiyatı*: {entry_price:.2f} USDT\n"
            f"🔻 *Stop-Loss*: {stop_loss:.2f} USDT\n\n"
            f"🎯 *Hedefler:*\n"
            f" - TP1: {tp1:.2f} USDT (+{tp1_percent}%)\n"
            f" - TP2: {tp2:.2f} USDT (+{tp2_percent}%)\n"
            f" - TP3: {tp3:.2f} USDT (+{tp3_percent}%)"
        )
    else:
        entry_price = latest_close
        stop_loss = entry_price * (1 + stop_loss_percent / 100)
        tp1 = entry_price * (1 - tp1_percent / 100)
        tp2 = entry_price * (1 - tp2_percent / 100)
        tp3 = entry_price * (1 - tp3_percent / 100)

        signal = (
            f"🔴 *Satım Sinyali*: {symbol} {interval}\n\n"
            f"💰 *Giriş Fiyatı*: {entry_price:.2f} USDT\n"
            f"🔺 *Stop-Loss*: {stop_loss:.2f} USDT\n\n"
            f"🎯 *Hedefler:*\n"
            f" - TP1: {tp1:.2f} USDT (-{tp1_percent}%)\n"
            f" - TP2: {tp2:.2f} USDT (-{tp2_percent}%)\n"
            f" - TP3: {tp3:.2f} USDT (-{tp3_percent}%)"
        )

    return signal

# Telegram bot komutu
@bot.message_handler(commands=['islem_stratejisi'])
def send_trade_levels(message):
    try:
        args = message.text.split()
        if len(args) != 3:
            bot.send_message(message.chat.id, "Kullanım: /islem_stratejisi [COIN] [ZAMAN_DILIMI] (Örn: /islem_stratejisi BTC 1h)")
            return

        symbol = args[1].upper()
        interval = args[2]
        trade_levels = calculate_trade_levels(symbol, interval)
        bot.send_message(message.chat.id, trade_levels, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Bir hata oluştu: {e}")




# CoinDesk RSS Feed URL
COINDESK_RSS_URL = "https://www.coindesk.com/arc/outboundfeeds/rss/"

# Kullanıcı veritabanı dosyası
USER_DB_FILE = "user_data.json"

def check_payment(user_id):
    headers = {
        "X-MBX-APIKEY": "your_api_key_here"
    }
    params = {
        "asset": "USDT",  # Specify the asset you want to check
        "status": 1       # Optional: specify the status of the deposit
    }

    try:
        response = requests.get("https://api.binance.com/sapi/v1/deposit/hisrec", headers=headers, params=params)
        response.raise_for_status()  # Raises an error for bad responses
        deposits = response.json()

        for deposit in deposits:
            if deposit["status"] == 1 and deposit["coin"] == "USDT":
                amount = float(deposit["amount"])
                if amount >= 50:
                    extend_membership(user_id)
                    return True

        return False

    except Exception as e:
        print(f"Ödeme kontrol hatası: {e}")
        return False
# Hata mesajı gönderme fonksiyonu
def send_error_message(chat_id, message):
    bot.send_message(chat_id, f"❌ Hata: {message}")

# /odeme komutu ile ödeme bilgilerini göster
@bot.message_handler(commands=['odeme'])
def show_payment_screen(message):
    bagis_adresi = "Tron(TRC20) \n TXfk17GRxQjE2CHKSkZk3navy3UKATxPzC"  # Binance USDT cüzdan adresiniz
    odeme_miktari = 50  # Üyelik ücreti (örneğin 50 USDT)

    message_text = (
        "💳 *Üyelik Yenileme*\n\n"
        f"Üyeliğinizi 30 gün boyunca uzatmak için {odeme_miktari} USDT ödeyin.\n\n"
        f"📥 *Cüzdan Adresi*: {bagis_adresi}\n\n"
        "Ödeme yaptıktan sonra üyeliğinizi yenilemek için aşağıdaki butona tıklayın."
    )

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✅ Ödeme Yaptım", callback_data=f"check_payment_{message.chat.id}"))

    bot.send_message(message.chat.id, message_text, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(commands=['kalan_sure'])
def show_remaining_time(message):
    user_id = str(message.chat.id)
    print(f"Kullanıcı ID: {user_id}")
    user_info = membership_data.get(user_id)

    if not user_info:
        print("Üyelik bilgisi bulunamadı.")
        bot.send_message(message.chat.id, "❌ Üyelik kaydınız bulunamadı. /kayit komutu ile kayıt olabilirsiniz.")
        return

    print(f"Üyelik bilgisi: {user_info}")
    try:
        expiry = datetime.fromisoformat(user_info["expiry"])
        now = datetime.now()
        print(f"Üyelik bitiş tarihi: {expiry}")
        print(f"Şu anki zaman: {now}")
        
        if expiry > now:
            remaining_time = expiry - now
            days, seconds = remaining_time.days, remaining_time.seconds
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            bot.send_message(message.chat.id, f"⏳ Üyeliğinizin bitmesine {days} gün, {hours} saat, {minutes} dakika kaldı.")
        else:
            bot.send_message(message.chat.id, "❌ Üyelik süreniz dolmuştur. /odeme komutu ile üyeliğinizi yenileyebilirsiniz.")
    except Exception as e:
        print(f"Hata oluştu: {e}")
        bot.send_message(message.chat.id, f"❌ Bir hata oluştu: {e}")



# /kalan_sure komutu ile üyelik süresini göster
@bot.message_handler(commands=['kullanici_sil'])
def delete_user(message):
    if not is_admin(message.chat.id):
        bot.send_message(message.chat.id, "❌ Bu komutu kullanmaya yetkiniz yok.")
        return

    args = message.text.split()
    if len(args) != 2:
        bot.send_message(message.chat.id, "Kullanım: /kullanici_sil [user_id]")
        return

    user_id = args[1]
    if user_id in membership_data:
        del membership_data[user_id]
        save_membership_data(membership_data)
        bot.send_message(message.chat.id, f"✅ {user_id} kullanıcı kaydı silindi.")
    else:
        # This line is correctly indented
        bot.send_message(message.chat.id, f"❌ {user_id} için kullanıcı kaydı bulunamadı.")


# Function to load membership data
def load_membership_data():
    if not os.path.exists("membership_data.json"):
        with open("membership_data.json", "w") as f:
            json.dump({}, f)
    with open("membership_data.json", "r") as f:
        return json.load(f)

# Load membership data at the start of your script
membership_data = load_membership_data()



# Üyelik veritabanını kaydet
def save_membership_data(data):
    with open("membership_data.json", "w") as f:
        json.dump(data, f, indent=4)

# Üyelik veritabanını yükle
def load_membership_data():
    if not os.path.exists("membership_data.json"):
        with open("membership_data.json", "w") as f:
            json.dump({}, f)
    with open("membership_data.json", "r") as f:
        return json.load(f)


# Kullanıcı veritabanını yükle veya oluştur
def load_user_data():
    if not os.path.exists(USER_DB_FILE):
        with open(USER_DB_FILE, "w") as f:
            json.dump({}, f)
    with open(USER_DB_FILE, "r") as f:
        return json.load(f)

# Kullanıcı verilerini kaydet
def save_user_data(data):
    with open(USER_DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

# Kullanıcı veritabanı
user_data = load_user_data()

# Kullanıcı fiyat alarmları
alarms = {}

# Coin sembollerine karşılık gelen emoji listesi
coin_emojis = {
    "BTC": "₿", "ETH": "Ξ", "BNB": "Ⓝ", "XRP": "✕", "USDT": "💵",
    "SOL": "◎", "DOGE": "Ð", "USDC": "💲", "ADA": "₳", "DOT": "⦾",
    "MATIC": "M", "AVAX": "🅰", "TRX": "T", "LTC": "Ł", "NEO": "𝔸",
    "EOS": "ε", "XLM": "☆", "LINK": "🔗", "BCH": "Ƀ", "ETC": "⎐",
    "XMR": "𝕎", "ZEC": "ⓩ", "DASH": "Đ", "ATOM": "⚛", "VET": "𝔽"
}

# Risk profiline göre yatırım stratejileri
investment_strategies = {
    "boga": {
        "dusuk_risk": (
            "🚀 *Boğa Piyasası - Düşük Risk Stratejisi:*\n\n"
            "- 💼 Portföyünüzün %60'ını Bitcoin (BTC) ve Ethereum (ETH) gibi büyük coinlere yatırın.\n"
            "- 🏦 %30'unu stablecoin'lerde (USDT, USDC) tutun.\n"
            "- 📈 %10'unu düşük riskli altcoinlere ayırabilirsiniz."
        ),
        "orta_risk": (
            "🚀 *Boğa Piyasası - Orta Risk Stratejisi:*\n\n"
            "- 💼 Portföyünüzün %40'ını BTC ve ETH'ye yatırın.\n"
            "- 🚀 %40'ını orta büyüklükteki altcoinlere ayırın.\n"
            "- 📊 %20'sini DeFi ve NFT projelerine yatırabilirsiniz."
        ),
        "yuksek_risk": (
            "🚀 *Boğa Piyasası - Yüksek Risk Stratejisi:*\n\n"
            "- 💎 %50'sini yüksek potansiyelli altcoinlere yatırın.\n"
            "- 🚀 %30'unu BTC ve ETH'ye ayırın.\n"
            "- 🎲 %20'sini kısa vadeli fırsatlara yatırabilirsiniz."
        ),
    },
    "ayi": {
        "dusuk_risk": (
            "🐻 *Ayı Piyasası - Düşük Risk Stratejisi:*\n\n"
            "- 🏦 Portföyünüzün %80'ini stablecoin'lerde (USDT, USDC) tutun.\n"
            "- 💼 %20'sini BTC ve ETH'ye yatırın.\n"
            "- ⏳ Uzun vadeli düşünün ve riskten kaçının."
        ),
        "orta_risk": (
            "🐻 *Ayı Piyasası - Orta Risk Stratejisi:*\n\n"
            "- 🏦 %60'ını stablecoin'lerde tutun.\n"
            "- 💼 %30'unu BTC ve ETH'ye yatırın.\n"
            "- 📉 %10'unu düşük riskli altcoinlere ayırabilirsiniz."
        ),
        "yuksek_risk": (
            "🐻 *Ayı Piyasası - Yüksek Risk Stratejisi:*\n\n"
            "- ⚠️ Yüksek riskli yatırımlardan kaçının.\n"
            "- 💼 %70'ini stablecoin'lerde tutun.\n"
            "- 📉 %30'unu güvenilir projelere ayırabilirsiniz."
        ),
    },
    "notr": {
        "dusuk_risk": (
            "⚖️ *Nötr Piyasa - Düşük Risk Stratejisi:*\n\n"
            "- 💼 Portföyünüzün %70'ini BTC ve ETH'ye yatırın.\n"
            "- 🏦 %20'sini stablecoin'lerde tutun.\n"
            "- 📊 %10'unu düşük riskli projelere ayırabilirsiniz."
        ),
        "orta_risk": (
            "⚖️ *Nötr Piyasa - Orta Risk Stratejisi:*\n\n"
            "- 💼 %50'sini BTC ve ETH'ye yatırın.\n"
            "- 🚀 %30'unu altcoinlere ayırın.\n"
            "- 📊 %20'sini DeFi projelerine yatırabilirsiniz."
        ),
        "yuksek_risk": (
            "⚖️ *Nötr Piyasa - Yüksek Risk Stratejisi:*\n\n"
            "- 🚀 %40'ını BTC ve ETH'ye yatırın.\n"
            "- 💎 %40'ını altcoinlere ayırın.\n"
            "- 🎲 %20'sini kısa vadeli fırsatlara yatırabilirsiniz."
        ),
    },
}

# Binance API'den Kline (OHLCV) verisi al
def get_kline_data(symbol, interval, limit=50):
    try:
        params = {"symbol": f"{symbol}USDT", "interval": interval, "limit": limit}
        response = requests.get(BINANCE_KLINE_URL, params=params)
        response.raise_for_status()  # Eğer hata varsa, exception fırlatılacak
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API hatası: {e}")
        return []

@bot.message_handler(commands=['fiyatlar'])
def show_coin_list(message):
    try:
        response = requests.get(BINANCE_API_URL)
        response.raise_for_status()
        binance_data = response.json()
        
        markup = InlineKeyboardMarkup()
        count = 0
        for item in binance_data:
            if item['symbol'].endswith('USDT') and count < 50:
                symbol = item['symbol'].replace("USDT", "")
                price = float(item['lastPrice'])
                button_text = f"{symbol} - {price:.2f} USDT"
                markup.add(InlineKeyboardButton(button_text, callback_data=f"coin_{symbol}"))
                count += 1
        
        bot.send_message(message.chat.id, "Lütfen bir coin seçin:", reply_markup=markup)
    except Exception as e:
        send_error_message(message.chat.id, str(e))

# /kayit komutu ile kullanıcı kaydı ve 1 günlük deneme süresi
@bot.message_handler(commands=['kayit'])
def register_user(message):
    user_id = str(message.chat.id)
    username = message.chat.username or f"Anonim_{user_id}"

    # Kullanıcı zaten kayıtlıysa
    if user_id in membership_data and is_premium_user(user_id):
        bot.send_message(message.chat.id, "✅ Zaten aktif bir üyeliğiniz var.")
        return

    # 1 günlük deneme süresi ver
    grant_trial(user_id, username)
    bot.send_message(message.chat.id, f"🎉 1 günlük deneme süreniz başladı! Tüm özellikleri kullanabilirsiniz, @{username}.")


# Üyelik veritabanını yükle
membership_data = load_membership_data()

# Kullanıcıya 1 günlük deneme süresi verme
def grant_trial(user_id, username):
    now = datetime.now()
    trial_end = now + timedelta(days=1)
    membership_data[user_id] = {"username": username, "status": "active", "expiry": trial_end.isoformat()}
    save_membership_data(membership_data)


def is_admin(user_id):
    admin_ids = ["1022198097"]  # Buraya kendi chat_id'nizi yazın
    return str(user_id) in admin_ids

@bot.message_handler(commands=['sure_uzat'])
def extend_user_membership(message):
    if not is_admin(message.chat.id):
        bot.send_message(message.chat.id, "❌ Bu komutu kullanmaya yetkiniz yok.")
        return

    args = message.text.split()
    if len(args) != 3:
        bot.send_message(message.chat.id, "Kullanım: /sure_uzat [user_id] [gun_sayisi] (Örn: /sure_uzat 123456789 30)")
        return

    user_id = args[1]
    try:
        days = int(args[2])
    except ValueError:
        bot.send_message(message.chat.id, "❌ Geçerli bir gün sayısı girin.")
        return

    user_info = membership_data.get(user_id)
    if not user_info:
        bot.send_message(message.chat.id, f"❌ {user_id} için kullanıcı kaydı bulunamadı.")
        return

    expiry = datetime.fromisoformat(user_info["expiry"])
    new_expiry = expiry + timedelta(days=days)
    membership_data[user_id]["expiry"] = new_expiry.isoformat()
    save_membership_data(membership_data)

    bot.send_message(message.chat.id, f"✅ {user_id} için üyelik süresi {days} gün uzatıldı. Yeni bitiş tarihi: {new_expiry.strftime('%Y-%m-%d %H:%M:%S')}")

def is_admin(user_id):
    admin_ids = ["1022198097"]  # Buraya kendi chat_id'nizi yazın
    return str(user_id) in admin_ids

@bot.message_handler(commands=['id'])
def get_id(message):
    bot.send_message(message.chat.id, f"Chat ID'niz: {message.chat.id}", parse_mode="Markdown")

@bot.message_handler(commands=['sure_uzat'])
def extend_user_membership(message):
    print(f"Komut çağrıldı: {message.text}")
    print(f"User ID: {message.chat.id}")

    if not is_admin(message.chat.id):
        print("Yetkisiz kullanıcı.")
        bot.send_message(message.chat.id, "❌ Bu komutu kullanmaya yetkiniz yok.")
        return

    args = message.text.split()
    if len(args) != 3:
        print("Hatalı kullanım formatı.")
        bot.send_message(message.chat.id, "Kullanım: /sure_uzat [user_id] [gun_sayisi]")
        return

    user_id = args[1]
    try:
        days = int(args[2])
    except ValueError:
        print("Geçersiz gün sayısı.")
        bot.send_message(message.chat.id, "❌ Geçerli bir gün sayısı girin.")
        return

    user_info = membership_data.get(user_id)
    if not user_info:
        print(f"Kullanıcı bulunamadı: {user_id}")
        bot.send_message(message.chat.id, f"❌ {user_id} için kullanıcı kaydı bulunamadı.")
        return

    try:
        expiry = datetime.fromisoformat(user_info["expiry"])
    except Exception as e:
        print(f"Tarih format hatası: {e}")
        bot.send_message(message.chat.id, "❌ Tarih formatı hatası.")
        return

    new_expiry = expiry + timedelta(days=days)
    membership_data[user_id]["expiry"] = new_expiry.isoformat()
    save_membership_data(membership_data)

    print(f"Üyelik uzatıldı: {user_id} için {days} gün.")
    bot.send_message(message.chat.id, f"✅ {user_id} için üyelik süresi {days} gün uzatıldı. Yeni bitiş tarihi: {new_expiry.strftime('%Y-%m-%d %H:%M:%S')}")


# /kullanicilar komutu ile tüm kullanıcıları listele (Sadece admin için)
@bot.message_handler(commands=['kullanicilar'])
def list_users(message):
    admin_id = "1022198097"  # Buraya kendi chat_id'nizi yazın

    if str(message.chat.id) != admin_id:
        bot.send_message(message.chat.id, "❌ Bu komutu kullanmaya yetkiniz yok.")
        return

    if not membership_data:
        bot.send_message(message.chat.id, "Kayıtlı kullanıcı bulunmamaktadır.")
        return

    user_list = ""
    for user_id, info in membership_data.items():
        username = info.get("username", "Bilinmiyor")
        expiry = info.get("expiry", "Bilinmiyor")
        user_list += f"🆔 {user_id} - @{username} - Bitiş: {expiry}\n"

    bot.send_message(message.chat.id, f"📋 *Kayıtlı Kullanıcılar:*\n\n{user_list}", parse_mode="Markdown")

@bot.message_handler(commands=['kullanici_sil'])
def delete_user(message):
    if not is_admin(message.chat.id):
        bot.send_message(message.chat.id, "❌ Bu komutu kullanmaya yetkiniz yok.")
        return

    args = message.text.split()
    if len(args) != 2:
        bot.send_message(message.chat.id, "Kullanım: /kullanici_sil [user_id]")
        return

    user_id = args[1]
    if user_id in membership_data:
        del membership_data[user_id]
        save_membership_data(membership_data)
        bot.send_message(message.chat.id, f"✅ {user_id} kullanıcı kaydı silindi.")
    else:
        # This line is correctly indented
        bot.send_message(message.chat.id, f"❌ {user_id} için kullanıcı kaydı bulunamadı.")

@bot.message_handler(commands=['yenile'])
def restart_bot(message):
    if not is_admin(message.chat.id):
        bot.send_message(message.chat.id, "❌ Bu komutu kullanmaya yetkiniz yok.")
        return

    bot.send_message(message.chat.id, "🔄 Bot yeniden başlatılıyor...")
    os.execv(sys.executable, ['python'] + sys.argv)



@bot.message_handler(commands=['sure_uzat'])
def extend_user_membership(message):
    if not is_admin(message.chat.id):
        bot.send_message(message.chat.id, "❌ Bu komutu kullanmaya yetkiniz yok.")
        return

    args = message.text.split()
    if len(args) != 3:
        bot.send_message(message.chat.id, "Kullanım: /sure_uzat [user_id] [gun_sayisi]")
        return

    user_id = args[1]
    try:
        days = int(args[2])
    except ValueError:
        bot.send_message(message.chat.id, "❌ Geçerli bir gün sayısı girin.")
        return

    user_info = membership_data.get(user_id)
    if not user_info:
        bot.send_message(message.chat.id, f"❌ {user_id} için kullanıcı kaydı bulunamadı.")
        return

    expiry = datetime.fromisoformat(user_info["expiry"])
    new_expiry = expiry + timedelta(days=days)
    membership_data[user_id]["expiry"] = new_expiry.isoformat()
    save_membership_data(membership_data)

    bot.send_message(message.chat.id, f"✅ {user_id} için üyelik süresi {days} gün uzatıldı. Yeni bitiş tarihi: {new_expiry.strftime('%Y-%m-%d %H:%M:%S')}")


# Üyelik süresini kontrol etme
def is_premium_user(user_id):
    user_info = membership_data.get(str(user_id))
    if not user_info:
        return False

    expiry = datetime.fromisoformat(user_info["expiry"])
    return expiry > datetime.now()

# Üyeliği 30 gün uzatma
def extend_membership(user_id):
    now = datetime.now()
    new_expiry = now + timedelta(days=30)
    membership_data[user_id] = {"status": "active", "expiry": new_expiry.isoformat()}
    save_membership_data(membership_data)



# /grafik komutu ile mum grafiği çiz
@bot.message_handler(commands=['grafik'])
def plot_candlestick_chart(message):
    args = message.text.split()
    if len(args) != 3:
        bot.send_message(message.chat.id, "Kullanım: /grafik [COIN] [ZAMAN_DİLİMİ]\nÖrnek: /grafik BTC 1h")
        return

    symbol = args[1].upper()
    interval = args[2]

    kline_data = get_kline_data(symbol, interval, limit=50)
    if not kline_data:
        bot.send_message(message.chat.id, f"❌ {symbol} için {interval} verisi alınamadı.")
        return

    # Veriyi DataFrame'e dönüştür
    df = pd.DataFrame(kline_data, columns=["timestamp", "open", "high", "low", "close", "volume", "close_time", "quote_asset_volume", "number_of_trades", "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit='ms')
    df.set_index("timestamp", inplace=True)
    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float)

    # Mum grafiğini çiz
    mpf.plot(df, type='candle', style='charles', title=f"{symbol} Fiyat Grafiği ({interval})", ylabel="Fiyat (USDT)", volume=True, savefig='candlestick.png')

    # Grafiği gönder
    with open('candlestick.png', 'rb') as photo:
        bot.send_photo(message.chat.id, photo)

    # Geçici dosyayı sil
    os.remove('candlestick.png')

# Teknik indikatörleri hesapla ve göster
@bot.callback_query_handler(func=lambda call: call.data.startswith("indicators_"))
def show_technical_indicators(call):
    _, symbol, interval = call.data.split("_")
    kline_data = get_kline_data(symbol, interval, limit=100)

    if not kline_data:
        bot.send_message(call.message.chat.id, f"❌ {symbol} için {interval} verisi alınamadı.")
        return

    # Veriyi DataFrame'e dönüştür
    df = pd.DataFrame(kline_data, columns=["timestamp", "open", "high", "low", "close", "volume", "close_time", "quote_asset_volume", "number_of_trades", "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"])
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)

    # RSI hesapla
    df["RSI"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()

    # MACD hesapla
    macd = ta.trend.MACD(df["close"])
    df["MACD"] = macd.macd()
    df["MACD Signal"] = macd.macd_signal()

    # Bollinger Bantları hesapla
    bb = ta.volatility.BollingerBands(df["close"], window=20, window_dev=2)
    df["BB Upper"] = bb.bollinger_hband()
    df["BB Lower"] = bb.bollinger_lband()

    # Son veriyi al
    latest_rsi = df["RSI"].iloc[-1]
    latest_macd = df["MACD"].iloc[-1]
    latest_macd_signal = df["MACD Signal"].iloc[-1]
    latest_bb_upper = df["BB Upper"].iloc[-1]
    latest_bb_lower = df["BB Lower"].iloc[-1]
    latest_close = df["close"].iloc[-1]

    message_text = (
        f"📊 *{symbol} {interval} Teknik İndikatörler:*\n\n"
        f"💹 *RSI*: {latest_rsi:.2f}\n"
        f"📈 *MACD*: {latest_macd:.2f}\n"
        f"📉 *MACD Sinyal Çizgisi*: {latest_macd_signal:.2f}\n"
        f"🔼 *Bollinger Üst Bandı*: {latest_bb_upper:.2f}\n"
        f"🔽 *Bollinger Alt Bandı*: {latest_bb_lower:.2f}\n"
        f"💰 *Güncel Fiyat*: {latest_close:.2f} USDT"
    )

    bot.send_message(call.message.chat.id, message_text, parse_mode="Markdown")

# /coin_bilgi komutu ile coin bilgisi göster
@bot.message_handler(commands=['coin_bilgi'])
def get_coin_info(message):
    args = message.text.split()
    if len(args) != 2:
        bot.send_message(message.chat.id, "Kullanım: /coin_bilgi [COIN]\nÖrnek: /coin_bilgi bitcoin")
        return

    coin = args[1].lower()

    try:
        response = requests.get(f"{COINGECKO_COIN_INFO_URL}{coin}")
        response.raise_for_status()
        data = response.json()

        name = data['name']
        symbol = data['symbol'].upper()
        market_cap = data['market_data']['market_cap']['usd']
        circulating_supply = data['market_data']['circulating_supply']
        description = data['description']['en'].split(".")[0]

        message_text = (
            f"🔎 *{name} ({symbol}) Bilgileri:*\n\n"
            f"💰 *Piyasa Değeri*: ${market_cap:,.2f}\n"
            f"🔄 *Dolaşımdaki Arz*: {circulating_supply:,.2f}\n"
            f"📝 *Proje Amacı*: {description}."
        )

        bot.send_message(message.chat.id, message_text, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Coin bilgisi alınırken hata oluştu: {e}")

# /piyasa_ozeti komutu ile piyasa genel görünümünü paylaş
@bot.message_handler(commands=['piyasa_ozeti'])
def get_market_summary(message):
    try:
        response = requests.get(COINGECKO_MARKET_URL)
        response.raise_for_status()
        data = response.json()["data"]

        total_market_cap = data["total_market_cap"]["usd"]
        total_volume = data["total_volume"]["usd"]
        btc_dominance = data["market_cap_percentage"]["btc"]

        market_message = (
            f"📊 *Kripto Piyasa Özeti:*\n\n"
            f"💰 *Toplam Piyasa Değeri*: ${total_market_cap:,.0f}\n"
            f"🔄 *24 Saatlik İşlem Hacmi*: ${total_volume:,.0f}\n"
            f"₿ *Bitcoin Dominansı*: {btc_dominance:.2f}%"
        )

        bot.send_message(message.chat.id, market_message, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Piyasa özeti alınırken bir hata oluştu: {e}")

# /fibonacci komutu ile Fibonacci geri çekilme seviyelerini hesapla
@bot.message_handler(commands=['fibonacci'])
def fibonacci_retracement(message):
    args = message.text.split()
    if len(args) != 3:
        bot.send_message(message.chat.id, "Kullanım: /fibonacci [COIN] [ZAMAN_DİLİMİ]\nÖrnek: /fibonacci BTC 1h")
        return

    symbol = args[1].upper()
    interval = args[2]

    kline_data = get_kline_data(symbol, interval, limit=50)
    
    if not kline_data:
        bot.send_message(message.chat.id, f"❌ {symbol} için {interval} verisi alınamadı.")
        return

    # Kapanış fiyatlarını al
    closes = [float(candle[4]) for candle in kline_data]
    high = max(closes)
    low = min(closes)

    # Fibonacci seviyeleri
    levels = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
    retracements = [(level, high - (high - low) * level) for level in levels]

    message_text = f"🔢 *{symbol} {interval} Fibonacci Geri Çekilme Seviyeleri:*\n\n"
    for level, price in retracements:
        message_text += f"🔹 %{level * 100:.1f}: {price:.2f} USDT\n"

    bot.send_message(message.chat.id, message_text, parse_mode="Markdown")

# /takvim komutu ile yaklaşan etkinlikleri göster
@bot.message_handler(commands=['takvim'])
def show_crypto_events(message):
    events = [
        {"name": "Ethereum Dencun Upgrade", "date": "2024-01-15", "details": "Ethereum ağ yükseltmesi."},
        {"name": "Bitcoin Halving", "date": "2024-04-20", "details": "Bitcoin blok ödül yarılanması."},
        {"name": "Cardano Summit 2024", "date": "2024-02-10", "details": "Cardano topluluk zirvesi."}
    ]

    message_text = "📅 *Yaklaşan Kripto Etkinlikleri:*\n\n"
    for event in events:
        message_text += f"🔹 *{event['name']}*\n📆 Tarih: {event['date']}\n📝 Detaylar: {event['details']}\n\n"

    bot.send_message(message.chat.id, message_text, parse_mode="Markdown")

# /kayit komutu ile kullanıcı kaydı ve 1 günlük deneme süresi
@bot.message_handler(commands=['kayit'])
def register_user(message):
    user_id = str(message.chat.id)
    
    if user_id in membership_data and is_premium_user(user_id):
        bot.send_message(message.chat.id, "✅ Zaten aktif bir üyeliğiniz var.")
        return

    grant_trial(user_id)
    bot.send_message(message.chat.id, "🎉 1 günlük deneme süreniz başladı! Tüm özellikleri kullanabilirsiniz.")

# /haberler komutu ile CoinDesk'ten kripto haberlerini paylaş
@bot.message_handler(commands=['haberler'])
def get_crypto_news(message):
    try:
        feed = feedparser.parse(COINDESK_RSS_URL)
        news_message = "📰 *CoinDesk Güncel Kripto Haberleri:*\n\n"

        # İlk 5 haberi listele
        for entry in feed.entries[:5]:
            title = entry.title
            link = entry.link
            news_message += f"🔹 [{title}]({link})\n\n"

        bot.send_message(message.chat.id, news_message, parse_mode="Markdown", disable_web_page_preview=True)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Haberler alınırken bir hata oluştu: {e}")


# Seçilen zaman dilimi için teknik indikatörler butonu ekle
@bot.callback_query_handler(func=lambda call: call.data.startswith("data_"))
def show_indicators_button(call):
    _, symbol, interval = call.data.split("_")
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📈 Teknik İndikatörler", callback_data=f"indicators_{symbol}_{interval}"))
    bot.send_message(call.message.chat.id, f"*{symbol}* için {interval} zaman dilimi seçildi. Teknik indikatörleri görmek için aşağıdaki butona tıklayın:", reply_markup=markup, parse_mode="Markdown")


# Piyasa trendini belirleme fonksiyonu
def get_market_trend():
    try:
        response = requests.get(COINGECKO_MARKET_URL)
        response.raise_for_status()
        data = response.json()["data"]

        total_market_cap_change = data["market_cap_change_percentage_24h_usd"]

        if total_market_cap_change > 1.0:
            return "boga"  # Yükseliş trendi
        elif total_market_cap_change < -1.0:
            return "ayi"   # Düşüş trendi
        else:
            return "notr"  # Yatay trend
    except Exception as e:
        print(f"Piyasa trendi alınırken hata oluştu: {e}")
        return "bilinmiyor"

# /bagis komutu ile bağış bilgilerini gönder
@bot.message_handler(commands=['bagis'])
def donate(message):
    bagis_adresi = "Tron(TRC20) \n TXfk17GRxQjE2CHKSkZk3navy3UKATxPzC"  # Binance USDT cüzdan adresiniz
    message_text = (
        "💝 *Bağış Yapmak İster misiniz?*\n\n"
        "Botun geliştirilmesine destek olmak için aşağıdaki cüzdan adresine USDT ile bağış yapabilirsiniz:\n\n"
        f"{bagis_adresi}\n\n"
        "Her bağış bizim için çok değerli! Teşekkür ederiz. 🙏"
    )

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Bağış Yaptım", callback_data="bagis_yapildi"))
    
    bot.send_message(message.chat.id, message_text, reply_markup=markup, parse_mode="Markdown")

# Bağış yapıldığını onaylama mesajı
@bot.callback_query_handler(func=lambda call: call.data == "bagis_yapildi")
def bagis_tesekkur(call):
    bot.send_message(call.message.chat.id, "🎉 Bağışınız için teşekkür ederiz! Desteklerinizle daha iyi hizmet verebileceğiz. 🙏")


# /fiyatlar komutu ile ilk 50 coinin fiyatlarını listele
@bot.message_handler(commands=['fiyatlar'])
def show_coin_list(message):
    try:
        response = requests.get(BINANCE_API_URL)
        response.raise_for_status()
        binance_data = response.json()
        
        markup = InlineKeyboardMarkup()
        count = 0
        for item in binance_data:
            if item['symbol'].endswith('USDT') and count < 50:
                symbol = item['symbol'].replace("USDT", "")
                price = float(item['lastPrice'])
                emoji = coin_emojis.get(symbol, '')
                button_text = f"{emoji} {symbol} - {price:.2f} USDT"
                markup.add(InlineKeyboardButton(button_text, callback_data=f"coin_{symbol}"))
                count += 1
        
        bot.send_message(message.chat.id, "Lütfen bir coin seçin:", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"Bir hata oluştu: {e}")

# /strateji komutu ile piyasa trendine göre strateji öner
@bot.message_handler(commands=['strateji'])
def investment_strategy(message):
    args = message.text.split()
    if len(args) != 2:
        bot.send_message(message.chat.id, "Kullanım: /strateji [dusuk_risk | orta_risk | yuksek_risk]")
        return

    risk_profile = args[1].lower()
    market_trend = get_market_trend()

    if market_trend == "bilinmiyor":
        bot.send_message(message.chat.id, "❌ Piyasa trendi belirlenemedi. Lütfen daha sonra tekrar deneyin.")
        return

    strategy = investment_strategies.get(market_trend, {}).get(risk_profile)

    if strategy:
        bot.send_message(message.chat.id, f"📈 *Piyasa Durumu*: {market_trend.capitalize()} Piyasası\n\n{strategy}", parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "❌ Geçerli bir risk profili girin: dusuk_risk, orta_risk veya yuksek_risk")

# Seçilen coin için zaman dilimi seçeneklerini göster
@bot.callback_query_handler(func=lambda call: call.data.startswith("coin_"))
def show_timeframe_options(call):
    symbol = call.data.split("_")[1]
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📉 Kısa Vadeli", callback_data=f"timeframe_{symbol}_short"))
    markup.add(InlineKeyboardButton("📊 Orta Vadeli", callback_data=f"timeframe_{symbol}_medium"))
    markup.add(InlineKeyboardButton("📈 Uzun Vadeli", callback_data=f"timeframe_{symbol}_long"))
    
    bot.send_message(call.message.chat.id, f"*{symbol}* için zaman dilimi seçin:", reply_markup=markup, parse_mode="Markdown")
# Seçilen coin için zaman dilimi seçeneklerini göster
@bot.callback_query_handler(func=lambda call: call.data.startswith("coin_"))
def show_timeframe_options(call):
    symbol = call.data.split("_")[1]
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📉 Kısa Vadeli", callback_data=f"timeframe_{symbol}_short"))
    markup.add(InlineKeyboardButton("📊 Orta Vadeli", callback_data=f"timeframe_{symbol}_medium"))
    markup.add(InlineKeyboardButton("📈 Uzun Vadeli", callback_data=f"timeframe_{symbol}_long"))
    
    bot.send_message(call.message.chat.id, f"*{symbol}* için zaman dilimi seçin:", reply_markup=markup, parse_mode="Markdown")

# Zaman dilimine göre detaylı hacim bilgisi göster
@bot.callback_query_handler(func=lambda call: call.data.startswith("timeframe_"))
def show_timeframe_details(call):
    _, symbol, timeframe = call.data.split("_")
    intervals = {
        "short": ["1m", "5m", "15m", "30m"],
        "medium": ["1h", "4h"],
        "long": ["1d", "1w", "1M"]
    }
    
    markup = InlineKeyboardMarkup()
    for interval in intervals[timeframe]:
        markup.add(InlineKeyboardButton(interval, callback_data=f"data_{symbol}_{interval}"))
    
    bot.send_message(call.message.chat.id, f"*{symbol}* için bir zaman dilimi seçin:", reply_markup=markup, parse_mode="Markdown")

# Seçilen zaman dilimi için trend analizi butonu ekle
@bot.callback_query_handler(func=lambda call: call.data.startswith("data_"))
def show_trend_analysis_button(call):
    _, symbol, interval = call.data.split("_")
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📉 Trend Analizi", callback_data=f"trend_{symbol}_{interval}"))
    bot.send_message(call.message.chat.id, f"*{symbol}* için {interval} zaman dilimi seçildi. Trend analizi yapmak için aşağıdaki butona tıklayın:", reply_markup=markup, parse_mode="Markdown")

# Trend analizi fonksiyonu
@bot.callback_query_handler(func=lambda call: call.data.startswith("trend_"))
def show_trend_analysis(call):
    _, symbol, interval = call.data.split("_")
    kline_data = get_kline_data(symbol, interval, limit=20)
    
    if not kline_data:
        bot.send_message(call.message.chat.id, f"❌ {symbol} için {interval} verisi alınamadı.")
        return

    close_prices = [float(candle[4]) for candle in kline_data]

    # Basit trend analizi: Son fiyat ile önceki fiyatların ortalamasını karşılaştır
    avg_price = sum(close_prices[:-1]) / len(close_prices[:-1])
    current_price = close_prices[-1]

    if current_price > avg_price:
        trend_message = f"✅ *{symbol} {interval} Trend Analizi: Yükseliş Eğilimi*"
    else:
        trend_message = f"🔻 *{symbol} {interval} Trend Analizi: Düşüş Eğilimi*"

    bot.send_message(call.message.chat.id, trend_message, parse_mode="Markdown")

# Zaman dilimi verilerini göster
@bot.callback_query_handler(func=lambda call: call.data.startswith("data_"))
def show_data(call):
    _, symbol, interval = call.data.split("_")
    kline_data = get_kline_data(symbol, interval)
    
    if kline_data:
        last_candle = kline_data[-1]
        price = float(last_candle[4])  # Kapanış fiyatı
        volume = float(last_candle[5])
        previous_volume = float(kline_data[-2][5])
        volume_change_percent = ((volume - previous_volume) / previous_volume) * 100 if previous_volume != 0 else 0

        message_text = (f"📊 *{symbol} {interval} Zaman Dilimi Bilgileri*\n"
                        f"💰 *Fiyat*: {price:.2f} USDT\n"
                        f"📈 *Hacim*: {volume:,.2f} USDT\n"
                        f"🔼 *Hacim Değişim*: {volume_change_percent:.2f}%")
        
        bot.send_message(call.message.chat.id, message_text, parse_mode="Markdown")
    else:
        bot.send_message(call.message.chat.id, f"{symbol} için {interval} verisi alınamadı.")


# /alarm komutu ile fiyat alarmı kur
@bot.message_handler(commands=['alarm'])
def set_price_alarm(message):
    args = message.text.split()
    if len(args) != 3:
        send_error_message(message.chat.id, "Kullanım: /alarm [COIN] [FİYAT] (Örn: /alarm BTC 30000)")
        return
    
    symbol, price = args[1].upper(), args[2]
    
    try:
        price = float(price)
    except ValueError:
        send_error_message(message.chat.id, "Fiyat sayısal bir değer olmalıdır.")
        return

    user_id = str(message.chat.id)
    if user_id not in alarms:
        alarms[user_id] = []
    
    alarms[user_id].append({"symbol": symbol, "price": price})
    bot.send_message(message.chat.id, f"🔔 {symbol} için {price} USDT fiyat alarmı kuruldu!")
# /ai_tahmin komutu ile fiyat tahmini
@bot.message_handler(commands=['ai_tahmin'])
def ai_tahmin(message):
    args = message.text.split()
    if len(args) != 3:
        bot.send_message(message.chat.id, "Kullanım: /ai_tahmin [COIN] [ZAMAN_DİLİMİ]\nÖrnek: /ai_tahmin BTC 1h")
        return

    symbol = args[1].upper()

    try:
        response = requests.get(BINANCE_API_URL)
        response.raise_for_status()
        data = response.json()

        coin_symbol = f"{symbol}USDT"
        coin_price = next((float(item["price"]) for item in data if item["symbol"] == coin_symbol), None)

        if coin_price is None:
            bot.send_message(message.chat.id, f"❌ {symbol} için fiyat bilgisi bulunamadı.")
            return

        # Basit rastgele tahmin simülasyonu
        prediction_percent = random.uniform(-3, 3)
        predicted_price = coin_price * (1 + prediction_percent / 100)

        message_text = (
            f"🔮 *{symbol} Tahmini:*\n\n"
            f"💰 *Güncel Fiyat*: {coin_price:.2f} USDT\n"
            f"📈 *Tahmini Değişim*: {prediction_percent:.2f}%\n"
            f"🔹 *Tahmini Fiyat*: {predicted_price:.2f} USDT"
        )

        bot.send_message(message.chat.id, message_text, parse_mode="Markdown")

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Fiyat tahmini yapılırken hata oluştu: {e}")

# Alarm kontrolü için thread
def check_alarms():
    while True:
        try:
            response = requests.get(BINANCE_API_URL)
            response.raise_for_status()
            binance_data = response.json()
            
            for user_id, user_alarms in list(alarms.items()):
                for alarm in user_alarms:
                    symbol = alarm["symbol"]
                    target_price = alarm["price"]
                    
                    for item in binance_data:
                        if item["symbol"] == f"{symbol}USDT":
                            current_price = float(item["lastPrice"])
                            if current_price >= target_price:
                                bot.send_message(user_id, f"🚨 {symbol} fiyatı {target_price} USDT'ye ulaştı! (Güncel Fiyat: {current_price} USDT)")
                                user_alarms.remove(alarm)
                                
                if not user_alarms:
                    del alarms[user_id]
                    
        except Exception as e:
            print(f"Alarm kontrol hatası: {e}")
        
        time.sleep(60)
# Yardım komutu
@bot.message_handler(commands=['yardim'])
def show_help(message):
    help_text = (
        "/kayit [SERMAYE] - Kayıt ol ve sermayeni belirle\n"
        "/fiyatlar - İlk 50 coinin fiyatlarını göster\n"
        "/alarm [COIN] [FİYAT] - Belirli bir fiyat için alarm kur\n"
        "/yardim - Komutlar hakkında bilgi al"
    )
    bot.send_message(message.chat.id, help_text)

@bot.message_handler(commands=['en_yuksek'])
def get_high_low_prices(message):
    args = message.text.split()
    
    if len(args) != 2:
        bot.send_message(message.chat.id, "Kullanım: /en_yuksek [COIN] (Örn: /en_yuksek BTC)")
        return
    
    symbol = args[1].upper()
    try:
        response = requests.get(BINANCE_API_URL)
        response.raise_for_status()
        data = response.json()
        
        for item in data:
            if item["symbol"] == f"{symbol}USDT":
                high_price = float(item["highPrice"])
                low_price = float(item["lowPrice"])
                
                emoji = coin_emojis.get(symbol, '')
                message_text = (
                    f"{emoji} *{symbol} 24 Saatlik Fiyat Bilgileri:*\n\n"
                    f"🔼 *En Yüksek Fiyat*: {high_price:.2f} USDT\n"
                    f"🔽 *En Düşük Fiyat*: {low_price:.2f} USDT"
                )
                
                bot.send_message(message.chat.id, message_text, parse_mode="Markdown")
                return
        
        bot.send_message(message.chat.id, f"❌ {symbol} için veri bulunamadı.")
    
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Bir hata oluştu: {e}")



    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Bir hata oluştu: {e}")

# Son 24 saatte en çok yükselen 5 coini listeler (USDT paritesi ve ilk 50 coini kapsar)
@bot.message_handler(commands=['en_yukselen'])
def get_top_gainers(message):
    try:
        response = requests.get(BINANCE_API_URL)
        response.raise_for_status()
        data = response.json()

        # Sadece USDT paritesine sahip olanları filtrele
        usdt_pairs = [coin for coin in data if coin['symbol'].endswith('USDT')]

        # İlk 50 coini al
        top_50 = usdt_pairs[:50]

        # En çok yükselenleri sırala
        top_gainers = sorted(top_50, key=lambda x: float(x['priceChangePercent']), reverse=True)[:5]

        message_text = "🚀 *Son 24 Saatte En Çok Yükselen 5 Coin:*\n\n"
        for coin in top_gainers:
            symbol = coin['symbol'].replace("USDT", "")
            price_change = float(coin['priceChangePercent'])
            emoji = coin_emojis.get(symbol, '')
            message_text += f"{emoji} *{symbol}*: %{price_change:.2f}\n"

        bot.send_message(message.chat.id, message_text, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Bir hata oluştu: {e}")

# /ai_portfoy komutu ile risk profiline uygun portföy önerisi
@bot.message_handler(commands=['ai_portfoy'])
def ai_portfoy(message):
    user_id = str(message.chat.id)
    if user_id not in user_data:
        bot.send_message(message.chat.id, "❌ Önce kayıt olmalısınız. /kayit [SERMAYE] komutu ile kayıt olun.")
        return

    balance = user_data[user_id].get("balance", 1000)

    # Risk profiline göre coin dağılımı
    low_risk = ["BTC", "ETH", "USDT"]
    medium_risk = ["BTC", "ETH", "BNB", "ADA", "USDT"]
    high_risk = ["ETH", "BNB", "SOL", "DOGE", "SHIB"]

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Düşük Risk", callback_data=f"portfoy_low_{balance}"))
    markup.add(InlineKeyboardButton("Orta Risk", callback_data=f"portfoy_medium_{balance}"))
    markup.add(InlineKeyboardButton("Yüksek Risk", callback_data=f"portfoy_high_{balance}"))

    bot.send_message(message.chat.id, "Risk profilinizi seçin:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("portfoy_"))
def show_portfoy(call):
    _, risk_level, balance = call.data.split("_")
    balance = float(balance)

    risk_profiles = {
        "low": ["BTC", "ETH", "USDT"],
        "medium": ["BTC", "ETH", "BNB", "ADA", "USDT"],
        "high": ["ETH", "BNB", "SOL", "DOGE", "SHIB"]
    }

    selected_coins = risk_profiles[risk_level]

    try:
        response = requests.get(BINANCE_API_URL)
        response.raise_for_status()
        data = response.json()

        prices = {item["symbol"]: float(item["price"]) for item in data}

        allocations = {}
        for coin in selected_coins:
            symbol = f"{coin}USDT"
            if symbol in prices:
                allocations[coin] = prices[symbol]

        message_text = f"🤖 *{risk_level.capitalize()} Risk Portföy Önerisi:*\n\n"
        for coin, price in allocations.items():
            amount = balance / len(allocations)
            quantity = amount / price
            message_text += f"🔹 *{coin}*: {quantity:.4f} adet (~{amount:.2f} USDT)\n"

        bot.send_message(call.message.chat.id, message_text, parse_mode="Markdown")

    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Portföy verisi alınırken hata oluştu: {e}")

# Son 24 saatte en çok düşen 5 coini listeler (USDT paritesi ve ilk 50 coini kapsar)
@bot.message_handler(commands=['en_dusen'])
def get_top_losers(message):
    try:
        response = requests.get(BINANCE_API_URL)
        response.raise_for_status()
        data = response.json()

        # Sadece USDT paritesine sahip olanları filtrele
        usdt_pairs = [coin for coin in data if coin['symbol'].endswith('USDT')]

        # İlk 50 coini al
        top_50 = usdt_pairs[:50]

        # En çok düşenleri sırala
        top_losers = sorted(top_50, key=lambda x: float(x['priceChangePercent']))[:5]

        message_text = "📉 *Son 24 Saatte En Çok Düşen 5 Coin:*\n\n"
        for coin in top_losers:
            symbol = coin['symbol'].replace("USDT", "")
            price_change = float(coin['priceChangePercent'])
            emoji = coin_emojis.get(symbol, '')
            message_text += f"{emoji} *{symbol}*: %{price_change:.2f}\n"

        bot.send_message(message.chat.id, message_text, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Bir hata oluştu: {e}")


# Son 24 saatte en çok düşen 5 coini listeler (USDT paritesi ve ilk 50 coini kapsar)
@bot.message_handler(commands=['en_dusen'])
def get_top_losers(message):
    try:
        response = requests.get(BINANCE_API_URL)
        response.raise_for_status()
        data = response.json()

        # Sadece USDT paritesine sahip olanları filtrele
        usdt_pairs = [coin for coin in data if coin['symbol'].endswith('USDT')]

        # İlk 50 coini al
        top_50 = usdt_pairs[:50]

        # En çok düşenleri sırala
        top_losers = sorted(top_50, key=lambda x: float(x['priceChangePercent']))[:5]

        message_text = "📉 *Son 24 Saatte En Çok Düşen 5 Coin:*\n\n"
        for coin in top_losers:
            symbol = coin['symbol'].replace("USDT", "")
            price_change = float(coin['priceChangePercent'])
            emoji = coin_emojis.get(symbol, '')
            message_text += f"{emoji} *{symbol}*: %{price_change:.2f}\n"

        bot.send_message(message.chat.id, message_text, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Bir hata oluştu: {e}")
    try:
        response = requests.get(BINANCE_API_URL)
        response.raise_for_status()
        data = response.json()

        top_losers = sorted(data, key=lambda x: float(x['priceChangePercent']))[:5]

        message_text = "📉 *Son 24 Saatte En Çok Düşen 5 Coin:*\n\n"
        for coin in top_losers:
            symbol = coin['symbol'].replace("USDT", "")
            price_change = float(coin['priceChangePercent'])
            emoji = coin_emojis.get(symbol, '')
            message_text += f"{emoji} *{symbol}*: %{price_change:.2f}\n"

        bot.send_message(message.chat.id, message_text, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Bir hata oluştu: {e}")

# 24 saatlik işlem hacmi en yüksek olan 5 coini gösterir (USDT paritesi ve ilk 50 coini kapsar)
@bot.message_handler(commands=['hacim_en_yuksek'])
def get_highest_volume(message):
    try:
        response = requests.get(BINANCE_API_URL)
        response.raise_for_status()
        data = response.json()

        # Sadece USDT paritesine sahip olanları filtrele
        usdt_pairs = [coin for coin in data if coin['symbol'].endswith('USDT')]

        # İlk 50 coini al
        top_50 = usdt_pairs[:50]

        # İşlem hacmine göre sırala
        highest_volume = sorted(top_50, key=lambda x: float(x['quoteVolume']), reverse=True)[:5]

        message_text = "💹 *Son 24 Saatte İşlem Hacmi En Yüksek 5 Coin:*\n\n"
        for coin in highest_volume:
            symbol = coin['symbol'].replace("USDT", "")
            volume = float(coin['quoteVolume'])
            emoji = coin_emojis.get(symbol, '')
            message_text += f"{emoji} *{symbol}*: {volume:,.2f} USDT\n"

        bot.send_message(message.chat.id, message_text, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Bir hata oluştu: {e}")

# Risk yönetimi hakkında tavsiyeler sunar
@bot.message_handler(commands=['risk_yonetimi'])
def risk_management_tips(message):
    tips = (
        "🛡️ *Risk Yönetimi İpuçları:*\n\n"
        "- 💼 *Portföyünüzü çeşitlendirin.* Farklı coinlere yatırım yaparak riskinizi azaltın.\n"
        "- ⛔ *Zarar durdur (Stop-Loss) kullanın.* Kaybınızı sınırlamak için stop-loss emirleri kullanın.\n"
        "- 📊 *Kaldıraçlı işlemlerden kaçının.* Yüksek kaldıraç yüksek risk getirir.\n"
        "- ⏳ *Uzun vadeli düşünün.* Piyasa dalgalanmalarına karşı sabırlı olun."
    )
    bot.send_message(message.chat.id, tips, parse_mode="Markdown")

# /ai_yorum komutu ile piyasa yorumu
@bot.message_handler(commands=['ai_yorum'])
def ai_yorum(message):
    args = message.text.split()
    if len(args) != 2:
        bot.send_message(message.chat.id, "Kullanım: /ai_yorum [COIN]\nÖrnek: /ai_yorum BTC")
        return

    symbol = args[1].upper()

    try:
        response = requests.get(BINANCE_API_URL)
        response.raise_for_status()
        data = response.json()

        coin_symbol = f"{symbol}USDT"
        coin_data = next((item for item in data if item["symbol"] == coin_symbol), None)

        if not coin_data:
            bot.send_message(message.chat.id, f"❌ {symbol} için veri bulunamadı.")
            return

        price = float(coin_data["lastPrice"])
        change_percent = float(coin_data["priceChangePercent"])

        if change_percent > 2:
            comment = f"{symbol} şu anda güçlü bir yükseliş trendinde. Alım fırsatlarını değerlendirin! 🚀"
        elif change_percent < -2:
            comment = f"{symbol} düşüş trendinde. Risk yönetimini ihmal etmeyin! 🔻"
        else:
            comment = f"{symbol} yatay bir seyir izliyor. Karar vermek için daha fazla sinyal beklemek iyi olabilir. ⚖️"

        message_text = (
            f"🤖 *{symbol} için AI Yorumu:*\n\n"
            f"💰 *Fiyat*: {price:.2f} USDT\n"
            f"📉 *24 Saatlik Değişim*: {change_percent:.2f}%\n\n"
            f"{comment}"
        )

        bot.send_message(message.chat.id, message_text, parse_mode="Markdown")

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Piyasa yorumu yapılırken hata oluştu: {e}")
# Kripto varlıklarının güvenliği hakkında ipuçları verir
@bot.message_handler(commands=['guvenlik_onerileri'])
def security_tips(message):
    tips = (
        "🔒 *Kripto Güvenlik İpuçları:*\n\n"
        "- 🔐 *Soğuk cüzdan kullanın.* Uzun vadeli yatırımlarınız için donanım cüzdanı tercih edin.\n"
        "- 🕵️‍♂️ *İki faktörlü kimlik doğrulama (2FA) kullanın.* Hesaplarınızı ek güvenlik katmanları ile koruyun.\n"
        "- 🚫 *Şüpheli bağlantılardan kaçının.* Phishing saldırılarına karşı dikkatli olun.\n"
        "- 🔑 *Özel anahtarlarınızı güvende tutun.* Kimseyle paylaşmayın."
    )
    bot.send_message(message.chat.id, tips, parse_mode="Markdown")


bot.set_my_commands([
    BotCommand("kayit", "Sermaye bilgisi ile kayıt ol"),
    BotCommand("strateji", "Yatırım stratejisi öner"),
    BotCommand("fiyatlar", "Coin fiyatlarını listele"),
    BotCommand("alarm", "Fiyat alarmı kur"),
    BotCommand("islem_stratejisi", "İşlem stratejisini göster"),
    BotCommand("kalan_sure", "Kalan üyelik sürenizi göster"),
    BotCommand("odeme", "Ödeme bilgilerini göster"),
    BotCommand("en_yuksek", "Seçilen coinin 24 saatlik en yüksek ve en düşük fiyatını göster"),
    BotCommand("piyasa_ozeti", "Kripto piyasasının genel görünümünü göster"),
    BotCommand("haberler", "CoinDesk'ten güncel kripto haberlerini paylaş"),
    BotCommand("en_yukselen", "Son 24 saatte en çok yükselen 5 coini göster"),
    BotCommand("grafik", "Coin fiyat grafiğini çiz"),
    BotCommand("fibonacci", "Fibonacci geri çekilme seviyelerini hesapla"),
    BotCommand("ai_portfoy", "Yapay zeka ile portföy önerisi"),
    BotCommand("ai_tahmin", "Yapay zeka ile fiyat tahmini yap"),
    BotCommand("kalan_sure", "Kalan üyelik sürenizi göster"),
    BotCommand("odeme", "Ödeme bilgilerini göster ve üyeliği yenile"),
    BotCommand("bagis", "Bot geliştirilmesine bağış yap"),
    BotCommand("ai_yorum", "Yapay zeka ile piyasa yorumu yap"),
    BotCommand("trend_sar", "Trend takip ve SAR analizi yap"),
    BotCommand("takvim", "Yaklaşan kripto etkinliklerini göster"),
    BotCommand("coin_bilgi", "Coin hakkında genel bilgileri göster"),
    BotCommand("en_dusen", "Son 24 saatte en çok düşen 5 coini göster"),
    BotCommand("hacim_en_yuksek", "24 saatlik işlem hacmi en yüksek 5 coini göster"),
    BotCommand("risk_yonetimi", "Risk yönetimi hakkında ipuçları"),
    BotCommand("guvenlik_onerileri", "Kripto varlıklarının güvenliği hakkında ipuçları"),
    BotCommand("yardim", "Yardım komutlarını göster"),
    BotCommand("strateji", "Arz-talep ve EMA kesişimlerine dayalı strateji analizi yap")
])


# Alarm kontrolü için thread başlat
alarm_thread = threading.Thread(target=check_alarms, daemon=True)
alarm_thread.start()

# Botu başlat
print("Bot çalışıyor...")
bot.polling()