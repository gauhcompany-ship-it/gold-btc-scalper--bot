import requests
import time
import threading
import os
from datetime import datetime
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

# ============================================================
# GLOBAL DATA STORAGE
# ============================================================

assets_data = {
    "XAUUSD": {},
    "BTCUSD": {}
}

# ============================================================
# API FUNCTIONS
# ============================================================

def get_gold_price():
    """Fetch live XAU/USD gold price"""

    try:
        url = "https://api.gold-api.com/price/XAU"

        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            print(f"Gold API Error: {response.status_code}")
            return None

        data = response.json()

        return float(data["price"])

    except Exception as e:
        print(f"Gold price error: {e}")
        return None


def get_bitcoin_price():
    """Fetch live BTC/USD price"""

    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"

        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            print(f"BTC API Error: {response.status_code}")
            return None

        data = response.json()

        return data["bitcoin"]["usd"]

    except Exception as e:
        print(f"Bitcoin price error: {e}")
        return None


def get_bitcoin_history():
    """Fetch BTC history for RSI"""

    try:
        url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=7"

        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            print(f"CoinGecko Error: {response.status_code}")
            return None

        data = response.json()

        prices = data.get("prices", [])

        if not prices:
            return None

        return [p[1] for p in prices[-30:]]

    except Exception as e:
        print(f"Bitcoin history error: {e}")
        return None


# ============================================================
# RSI CALCULATION
# ============================================================

def calculate_rsi(prices, period=14):

    if not prices or len(prices) < period + 1:
        return 50

    gains = []
    losses = []

    for i in range(1, len(prices)):

        change = prices[i] - prices[i - 1]

        if change > 0:
            gains.append(change)
        else:
            losses.append(abs(change))

    avg_gain = sum(gains[-period:]) / period if gains else 0
    avg_loss = sum(losses[-period:]) / period if losses else 0

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss

    rsi = 100 - (100 / (1 + rs))

    return round(rsi, 2)


# ============================================================
# SUPPORT & RESISTANCE
# ============================================================

def calculate_support_resistance(price, asset):

    if asset == "XAUUSD":
        support = round(price - 10, 2)
        resistance = round(price + 10, 2)

    else:
        support = round(price - 2000, 0)
        resistance = round(price + 2000, 0)

    return support, resistance


# ============================================================
# SIGNAL GENERATION
# ============================================================

def generate_signal(asset, price, rsi, support, resistance):

    near_support = abs(price - support) < (
        10 if asset == "XAUUSD" else 500
    )

    near_resistance = abs(price - resistance) < (
        10 if asset == "XAUUSD" else 500
    )

    signal = "HOLD"
    confidence = "Low"

    if rsi < 35 and near_support:
        signal = "BUY"
        confidence = "High"

    elif rsi > 65 and near_resistance:
        signal = "SELL"
        confidence = "High"

    elif rsi < 30:
        signal = "BUY"
        confidence = "Medium"

    elif rsi > 70:
        signal = "SELL"
        confidence = "Medium"

    # TP / SL

    if signal == "BUY":

        tp = round(price * 1.005, 2)
        sl = round(price * 0.995, 2)

    elif signal == "SELL":

        tp = round(price * 0.995, 2)
        sl = round(price * 1.005, 2)

    else:

        tp = price
        sl = price

    reasoning = f"RSI={rsi} | Support={support} | Resistance={resistance}"

    return signal, confidence, tp, sl, reasoning


# ============================================================
# BOT LOOP
# ============================================================

def trading_bot():

    print("=" * 60)
    print("🚀 AI DUAL SCALPER BOT STARTED")
    print("=" * 60)

    while True:

        try:

            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            print(f"\n[{current_time}] Updating market data...")

            # ====================================================
            # GOLD
            # ====================================================

            gold_price = get_gold_price()

            if gold_price:

                gold_rsi = 50

                gold_support, gold_resistance = calculate_support_resistance(
                    gold_price,
                    "XAUUSD"
                )

                signal, confidence, tp, sl, reasoning = generate_signal(
                    "XAUUSD",
                    gold_price,
                    gold_rsi,
                    gold_support,
                    gold_resistance
                )

                assets_data["XAUUSD"] = {
                    "price": gold_price,
                    "rsi": gold_rsi,
                    "support": gold_support,
                    "resistance": gold_resistance,
                    "signal": signal,
                    "confidence": confidence,
                    "take_profit": tp,
                    "stop_loss": sl,
                    "reasoning": reasoning,
                    "last_update": current_time
                }

                print(f"✅ XAUUSD: ${gold_price}")

            else:

                print("❌ Failed to fetch XAUUSD")

            time.sleep(2)

            # ====================================================
            # BITCOIN
            # ====================================================

            btc_price = get_bitcoin_price()

            btc_history = get_bitcoin_history()

            if btc_price:

                btc_rsi = calculate_rsi(btc_history)

                btc_support, btc_resistance = calculate_support_resistance(
                    btc_price,
                    "BTCUSD"
                )

                signal, confidence, tp, sl, reasoning = generate_signal(
                    "BTCUSD",
                    btc_price,
                    btc_rsi,
                    btc_support,
                    btc_resistance
                )

                assets_data["BTCUSD"] = {
                    "price": btc_price,
                    "rsi": btc_rsi,
                    "support": btc_support,
                    "resistance": btc_resistance,
                    "signal": signal,
                    "confidence": confidence,
                    "take_profit": tp,
                    "stop_loss": sl,
                    "reasoning": reasoning,
                    "last_update": current_time
                }

                print(f"✅ BTCUSD: ${btc_price}")

            else:

                print("❌ Failed to fetch BTCUSD")

        except Exception as e:

            print(f"Loop error: {e}")

        print("⏳ Waiting 60 seconds...\n")

        time.sleep(60)


# ============================================================
# HTML UI
# ============================================================

HTML = """

<!DOCTYPE html>
<html>
<head>
<title>AI Dual Scalper</title>

<style>

body{
    background:#0f172a;
    color:white;
    font-family:Arial;
    padding:20px;
}

.card{
    background:#111827;
    padding:20px;
    border-radius:20px;
    margin-bottom:20px;
}

.price{
    font-size:40px;
    color:gold;
}

.buy{
    color:#10b981;
}

.sell{
    color:#ef4444;
}

.hold{
    color:#f59e0b;
}

</style>

</head>

<body>

<h1>🤖 AI Dual Scalper Bot</h1>

<div class="card">

<h2>XAU/USD</h2>

<div class="price" id="goldPrice">$---</div>

<p>RSI: <span id="goldRsi">---</span></p>

<p>Signal:
<span id="goldSignal">WAITING</span>
</p>

<p id="goldReason">Loading...</p>

</div>

<div class="card">

<h2>BTC/USD</h2>

<div class="price" id="btcPrice">$---</div>

<p>RSI: <span id="btcRsi">---</span></p>

<p>Signal:
<span id="btcSignal">WAITING</span>
</p>

<p id="btcReason">Loading...</p>

</div>

<script>

async function updateData(){

    try{

        const response = await fetch('/api/data')

        const data = await response.json()

        // GOLD

        if(data.XAUUSD.price){

            document.getElementById("goldPrice").innerHTML =
            "$" + data.XAUUSD.price

            document.getElementById("goldRsi").innerHTML =
            data.XAUUSD.rsi

            document.getElementById("goldSignal").innerHTML =
            data.XAUUSD.signal

            document.getElementById("goldReason").innerHTML =
            data.XAUUSD.reasoning
        }

        // BTC

        if(data.BTCUSD.price){

            document.getElementById("btcPrice").innerHTML =
            "$" + data.BTCUSD.price

            document.getElementById("btcRsi").innerHTML =
            data.BTCUSD.rsi

            document.getElementById("btcSignal").innerHTML =
            data.BTCUSD.signal

            document.getElementById("btcReason").innerHTML =
            data.BTCUSD.reasoning
        }

    }catch(err){

        console.log(err)

    }

}

updateData()

setInterval(updateData, 5000)

</script>

</body>
</html>

"""


# ============================================================
# FLASK ROUTES
# ============================================================

@app.route("/")
def home():
    return render_template_string(HTML)


@app.route("/api/data")
def api_data():
    return jsonify(assets_data)


# ============================================================
# START BOT
# ============================================================

bot_thread = threading.Thread(
    target=trading_bot,
    daemon=True
)

bot_thread.start()

print("✅ Trading bot thread started")


# ============================================================
# RUN FLASK
# ============================================================

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )
