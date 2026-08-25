import os
import json
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

# ============================================================
# SETTINGS
# ============================================================

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

PRICE_MIN = 100
PRICE_MAX = 5000
DAILY_VOLUME_MIN = 100000

STATE_FILE = "alert_state.json"


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram secrets not found")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:
        r = requests.post(url, data=payload, timeout=20)
        print("Telegram:", r.status_code)

        if r.ok:
            return True

        print(r.text)
        return False

    except Exception as e:
        print("Telegram error:", e)
        return False


# ============================================================
# STATE
# ============================================================

def load_state():

    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)

    except Exception:
        return {}


def save_state(state):

    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ============================================================
# PART 1
# NSE EQ SHARES + DAILY DATA
# ============================================================

print("=" * 50)
print("PART 1")
print("NSE EQ SHARES + DAILY DATA")
print("=" * 50)

url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"

nse = pd.read_csv(url)

nse.columns = nse.columns.str.strip()

# केवल EQ shares
nse = nse[nse["SERIES"] == "EQ"].copy()

symbols = (
    nse["SYMBOL"]
    .dropna()
    .unique()
    .tolist()
)

print("Total NSE EQ Shares:", len(symbols))

yf_symbols = [x + ".NS" for x in symbols]

print("Yahoo Symbols:", len(yf_symbols))
print()
print("Downloading 1 Year Daily Data...")
print("Please wait...")


data = yf.download(
    yf_symbols,
    period="1y",
    interval="1d",
    group_by="ticker",
    auto_adjust=False,
    progress=True,
    threads=True
)

print()
print("=" * 50)
print("PART 1 COMPLETE")
print("=" * 50)

print("NSE EQ Shares:", len(symbols))
print("Downloaded Rows:", len(data))
print("Data Columns:", len(data.columns))

print()
print("Daily Data Download Complete")


# ============================================================
# PART 2
# WEEKLY BB LOWER BREAK
# ============================================================

print()
print("=" * 50)
print("PART 2 SCREENING STARTED")
print("=" * 50)

print("Total Shares to Search:", len(symbols))
print("Daily Volume Minimum:", DAILY_VOLUME_MIN)
print("Price Range:", PRICE_MIN, "-", PRICE_MAX)

results = []

valid_daily = 0
valid_weekly = 0
price_count = 0
volume_count = 0
bb_count = 0


for symbol in symbols:

    ticker = symbol + ".NS"

    try:

        if ticker not in data.columns.get_level_values(0):
            continue

        df = data[ticker].copy()

        if df.empty:
            continue

        df = df.dropna(subset=["Close", "High", "Low", "Volume"])

        if len(df) < 30:
            continue

        valid_daily += 1

        # ----------------------------------------------------
        # Current price
        # ----------------------------------------------------

        current_price = float(df["Close"].iloc[-1])

        if not (PRICE_MIN <= current_price <= PRICE_MAX):
            continue

        price_count += 1

        # ----------------------------------------------------
        # Daily volume
        # ----------------------------------------------------

        daily_volume = float(df["Volume"].iloc[-1])

        if daily_volume < DAILY_VOLUME_MIN:
            continue

        volume_count += 1

        # ----------------------------------------------------
        # Weekly data
        # ----------------------------------------------------

        weekly = pd.DataFrame({
            "Open": df["Open"].resample("W-FRI").first(),
            "High": df["High"].resample("W-FRI").max(),
            "Low": df["Low"].resample("W-FRI").min(),
            "Close": df["Close"].resample("W-FRI").last(),
            "Volume": df["Volume"].resample("W-FRI").sum()
        }).dropna()

        if len(weekly) < 21:
            continue

        valid_weekly += 1

        # ----------------------------------------------------
        # Weekly Bollinger Band
        # 20 Week SMA
        # 2 Standard Deviation
        # ----------------------------------------------------

        weekly["SMA20"] = (
            weekly["Close"]
            .rolling(20)
            .mean()
        )

        weekly["STD20"] = (
            weekly["Close"]
            .rolling(20)
            .std()
        )

        weekly["BB_LOWER"] = (
            weekly["SMA20"] -
            (2 * weekly["STD20"])
        )

        last = weekly.iloc[-1]

        if pd.isna(last["BB_LOWER"]):
            continue

        weekly_low = float(last["Low"])
        bb_lower = float(last["BB_LOWER"])
        weekly_high = float(last["High"])
        weekly_volume = float(last["Volume"])

        # ----------------------------------------------------
        # WEEKLY BB LOWER BREAK
        # ----------------------------------------------------

        if weekly_low >= bb_lower:
            continue

        bb_count += 1

        # ----------------------------------------------------
        # Average Weekly Volume
        # ----------------------------------------------------

        avg_weekly_volume = float(
            weekly["Volume"]
            .tail(20)
            .mean()
        )

        results.append({
            "NSE Code": symbol,
            "Price": round(current_price, 2),
            "Weekly Low": round(weekly_low, 2),
            "BB Lower": round(bb_lower, 2),
            "Weekly High": round(weekly_high, 2),
            "Weekly Volume": int(weekly_volume),
            "Avg Weekly Volume": int(avg_weekly_volume)
        })

    except Exception as e:

        print("Skip:", symbol, e)
        continue


# ============================================================
# SORT
# LOWEST AVG WEEKLY VOLUME FIRST
# ============================================================

results = sorted(
    results,
    key=lambda x: x["Avg Weekly Volume"]
)


print()
print("=" * 50)
print("SCREENING REPORT")
print("=" * 50)

print("Total Shares:", len(symbols))
print("Valid Daily Data:", valid_daily)
print("Valid Weekly Data:", valid_weekly)
print(
    f"Price ₹{PRICE_MIN}-₹{PRICE_MAX}:",
    price_count
)
print(
    "Daily Volume >= 1 Lakh:",
    volume_count
)
print("Weekly BB Lower Break:", bb_count)
print("FINAL SHARES:", len(results))

print("=" * 50)


# ============================================================
# WEEKLY HIGH LIST
# ============================================================

print()
print("Weekly High Alert List Ready")
print()

for i, item in enumerate(results, 1):

    print(
        i,
        item["NSE Code"],
        "Weekly High:",
        item["Weekly High"]
    )


# ============================================================
# TELEGRAM ALERT CHECK
# ============================================================

state = load_state()

print()
print("=" * 50)
print("TELEGRAM WEEKLY HIGH CHECK")
print("=" * 50)


for item in results:

    symbol = item["NSE Code"]

    weekly_high = item["Weekly High"]
    price = item["Price"]

    old = state.get(symbol, {})

    # --------------------------------------------------------
    # First time
    # --------------------------------------------------------

    if not old:

        state[symbol] = {
            "alert_sent": False,
            "weekly_high": weekly_high
        }

        continue

    # --------------------------------------------------------
    # Update weekly high
    # --------------------------------------------------------

    old_high = old.get("weekly_high", weekly_high)

    # --------------------------------------------------------
    # ALERT
    # --------------------------------------------------------

    if price > old_high and not old.get("alert_sent", False):

        message = (
            "🚨 WEEKLY HIGH BREAK\n\n"
            f"Stock: {symbol}\n"
            f"Price: ₹{price:.2f}\n"
            f"Weekly High: ₹{old_high:.2f}\n\n"
            "Weekly High टूट गया है."
        )

        if send_telegram(message):

            state[symbol]["alert_sent"] = True

            print(
                "ALERT SENT:",
                symbol
            )

    # Save latest high
    state[symbol]["weekly_high"] = weekly_high


# ============================================================
# SAVE STATE
# ============================================================

save_state(state)

print()
print("=" * 50)
print("PART 3 TEST FINISHED")
print("=" * 50)
