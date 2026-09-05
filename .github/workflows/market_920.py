import os
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime

# ============================================================
# TELEGRAM
# ============================================================

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

def send_telegram(message):
    if not TOKEN or not CHAT_ID:
        print("Telegram secrets missing")
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    r = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": message
        },
        timeout=30
    )

    print("Telegram:", r.status_code)

    if not r.ok:
        print(r.text)


# ============================================================
# NSE SECTOR DATA
# ============================================================

print("Downloading NSE sector data...")

headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://www.nseindia.com/"
}

session = requests.Session()
session.headers.update(headers)

session.get("https://www.nseindia.com", timeout=20)

sector_url = "https://www.nseindia.com/api/allIndices"

response = session.get(sector_url, timeout=30)
response.raise_for_status()

data = response.json()

rows = data.get("data", [])

sector_data = []

for x in rows:

    index_name = x.get("index", "")
    percent = x.get("percentChange")

    if percent is None:
        continue

    try:
        percent = float(percent)
    except:
        continue

    # केवल sectoral indices
    if index_name in [
        "NIFTY AUTO",
        "NIFTY BANK",
        "NIFTY FINANCIAL SERVICES",
        "NIFTY FMCG",
        "NIFTY IT",
        "NIFTY MEDIA",
        "NIFTY METAL",
        "NIFTY PHARMA",
        "NIFTY PRIVATE BANK",
        "NIFTY PSU BANK",
        "NIFTY REALTY",
        "NIFTY HEALTHCARE INDEX",
        "NIFTY OIL & GAS",
        "NIFTY CONSUMER DURABLES"
    ]:
        sector_data.append({
            "Sector": index_name,
            "Change": percent
        })


if not sector_data:
    raise Exception("NSE sector data नहीं मिला")


sector_df = pd.DataFrame(sector_data)

sector_df = sector_df.sort_values(
    "Change",
    ascending=False
)

strong_sector = sector_df.iloc[0]
weak_sector = sector_df.iloc[-1]

print()
print("STRONG SECTOR:")
print(strong_sector)

print()
print("WEAK SECTOR:")
print(weak_sector)


# ============================================================
# NSE EQ LIST
# ============================================================

eq_url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"

nse = pd.read_csv(eq_url)

nse.columns = nse.columns.str.strip()

nse = nse[nse["SERIES"] == "EQ"].copy()

symbols = (
    nse["SYMBOL"]
    .dropna()
    .unique()
    .tolist()
)

print()
print("NSE EQ Shares:", len(symbols))


# ============================================================
# FIND TOP SHARES
# ============================================================

# Sector → NSE stocks mapping
# NSE sector constituent pages/API

def get_sector_stocks(index_name):

    url = "https://www.nseindia.com/api/equity-stockIndices"

    params = {
        "index": index_name
    }

    r = session.get(
        url,
        params=params,
        timeout=30
    )

    if not r.ok:
        print("Sector stock error:", index_name, r.status_code)
        return []

    try:
        j = r.json()
        return j.get("data", [])
    except:
        return []


def get_top_stocks(index_name, top_n):

    stocks = get_sector_stocks(index_name)

    result = []

    for x in stocks:

        symbol = x.get("symbol")

        if not symbol:
            continue

        # Index row को हटाएँ
        if symbol.startswith("NIFTY"):
            continue

        percent = x.get("pChange")

        if percent is None:
            percent = x.get("perChange")

        try:
            percent = float(percent)
        except:
            continue

        result.append({
            "symbol": symbol,
            "change": percent
        })

    result = sorted(
        result,
        key=lambda x: x["change"],
        reverse=(top_n == 2)
    )

    return result[:top_n]


# ============================================================
# TOP 2 TEZI
# TOP 3 MANDI
# ============================================================

strong_stocks = get_top_stocks(
    strong_sector["Sector"],
    2
)

weak_stocks = get_top_stocks(
    weak_sector["Sector"],
    3
)


# ============================================================
# NSE ADVANCE / DECLINE
# ============================================================

advance = 0
decline = 0
unchanged = 0

try:

    market_url = "https://www.nseindia.com/api/marketStatus"

    # Broad market data
    r = session.get(
        "https://www.nseindia.com/api/live-analysis-variations",
        timeout=30
    )

    if r.ok:

        j = r.json()

        # NSE response structure बदल सकता है,
        # इसलिए अलग-अलग possible keys check करेंगे.

        for item in j.get("advancesDeclines", []):

            advance = item.get("advances", advance)
            decline = item.get("declines", decline)
            unchanged = item.get("unchanged", unchanged)

except Exception as e:

    print("Advance decline error:", e)


# अगर ऊपर से data नहीं मिला तो market breadth API try करें

if advance == 0 and decline == 0:

    try:

        r = session.get(
            "https://www.nseindia.com/api/market-data-pre-open?key=ALL",
            timeout=30
        )

        if r.ok:

            j = r.json()

            # उपलब्ध data से broad breadth निकालना
            for item in j.get("data", []):

                info = item.get("metadata", {})

                pchange = info.get("pChange")

                if pchange is None:
                    continue

                if pchange > 0:
                    advance += 1
                elif pchange < 0:
                    decline += 1
                else:
                    unchanged += 1

    except Exception as e:

        print("Breadth fallback error:", e)


# ============================================================
# A/D RATIO
# ============================================================

if decline > 0:
    ad_ratio = advance / decline
else:
    ad_ratio = advance


# ============================================================
# TELEGRAM MESSAGE
# ============================================================

now = datetime.now().strftime("%d-%m-%Y %H:%M")

message = (
    "📊 NSE 9:20 AM MARKET REPORT\n"
    f"🕘 {now}\n\n"

    "🟢 TEZI SECTOR\n"
    f"{strong_sector['Sector']} "
    f"+{strong_sector['Change']:.2f}%\n"
)

for i, stock in enumerate(strong_stocks, 1):

    message += (
        f"{i}. {stock['symbol']} "
        f"+{stock['change']:.2f}%\n"
    )


message += (
    "\n🔴 MANDI SECTOR\n"
    f"{weak_sector['Sector']} "
    f"{weak_sector['Change']:.2f}%\n"
)

for i, stock in enumerate(weak_stocks, 1):

    message += (
        f"{i}. {stock['symbol']} "
        f"{stock['change']:.2f}%\n"
    )


message += (
    "\n📈 NSE MARKET BREADTH\n"
    f"Advance: {advance}\n"
    f"Decline: {decline}\n"
    f"Unchanged: {unchanged}\n"
    f"A/D Ratio: {ad_ratio:.2f}"
)

print()
print("=" * 50)
print(message)
print("=" * 50)

send_telegram(message)
