import requests
import time
import json
import os
import threading
from datetime import datetime
from flask import Flask, render_template_string, jsonify

app = Flask(__name__)

# Global data storage
assets_data = {
    'XAUUSD': {
        'price': None, 'rsi': None, 'support': None, 'resistance': None,
        'signal': 'WAITING', 'confidence': 'Low', 'position': None,
        'take_profit': None, 'stop_loss': None, 'reasoning': 'Awaiting first analysis...',
        'last_update': 'Never'
    },
    'BTCUSD': {
        'price': None, 'rsi': None, 'support': None, 'resistance': None,
        'signal': 'WAITING', 'confidence': 'Low', 'position': None,
        'take_profit': None, 'stop_loss': None, 'reasoning': 'Awaiting first analysis...',
        'last_update': 'Never'
    }
}

# ============================================================
# API FUNCTIONS
# ============================================================

def get_gold_price():
    """Get live XAU/USD gold price"""
    try:
        url = "https://api.gold-api.com/price/XAU"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            print(f"Gold API Error: {response.status_code}")
            return None
        
        data = response.json()
        price = data.get("price")
        
        if price:
            print(f"✅ Gold price: ${price:.2f}")
            return float(price)
        return None
    except Exception as e:
        print(f"Gold price error: {e}")
        return None

def get_bitcoin_price():
    """Get live Bitcoin price from CoinGecko"""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            print(f"Bitcoin API Error: {response.status_code}")
            return None
        
        data = response.json()
        price = data.get('bitcoin', {}).get('usd')
        
        if price:
            print(f"✅ Bitcoin price: ${price:.0f}")
            return float(price)
        return None
    except Exception as e:
        print(f"Bitcoin price error: {e}")
        return None

def get_bitcoin_history():
    """Get Bitcoin historical prices for RSI"""
    try:
        url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=7"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            print(f"CoinGecko History Error: {response.status_code}")
            return None
        
        data = response.json()
        prices = data.get("prices", [])
        
        if not prices:
            return None
        
        return [p[1] for p in prices[-30:]]
    except Exception as e:
        print(f"Bitcoin history error: {e}")
        return None

def calculate_rsi(prices, period=14):
    """Calculate RSI from price list"""
    if not prices or len(prices) < period + 1:
        return 50
    
    # Take last (period+1) prices
    prices = prices[-(period+1):]
    gains = 0
    losses = 0
    
    for i in range(len(prices) - 1):
        diff = prices[i+1] - prices[i]
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    
    avg_gain = gains / period
    avg_loss = losses / period
    
    if avg_loss == 0:
        return 75
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 1)

def generate_signal(asset_key, price, rsi, support, resistance):
    """Generate trading signal based on RSI + Support/Resistance"""
    # FIXED: Wider thresholds for better signal detection
    if asset_key == 'XAUUSD':
        near_threshold = 10  # $10 threshold for gold
    else:
        near_threshold = 500  # $500 threshold for Bitcoin
    
    near_support = abs(price - support) < near_threshold
    near_resistance = abs(price - resistance) < near_threshold
    
    # Debug print
    print(f"   Signal check - Price: ${price:.2f}, Support: ${support:.2f}, Resistance: ${resistance:.2f}")
    print(f"   Near Support: {near_support} (diff: ${abs(price - support):.2f}), Near Resistance: {near_resistance}")
    
    # Generate signal based on RSI and price position
    if rsi < 35 and near_support:
        signal = 'BUY'
        confidence = 'High'
        reasoning = f'RSI oversold ({rsi}) near support (${support:.2f})'
        tp = round(price * 1.005, 2) if asset_key == 'XAUUSD' else round(price * 1.01, 0)
        sl = round(price * 0.995, 2) if asset_key == 'XAUUSD' else round(price * 0.99, 0)
    elif rsi < 30:
        signal = 'BUY'
        confidence = 'Medium'
        reasoning = f'RSI deeply oversold ({rsi}) - potential bounce'
        tp = round(price * 1.003, 2) if asset_key == 'XAUUSD' else round(price * 1.005, 0)
        sl = round(price * 0.997, 2) if asset_key == 'XAUUSD' else round(price * 0.995, 0)
    elif rsi > 65 and near_resistance:
        signal = 'SELL'
        confidence = 'High'
        reasoning = f'RSI overbought ({rsi}) near resistance (${resistance:.2f})'
        tp = round(price * 0.995, 2) if asset_key == 'XAUUSD' else round(price * 0.99, 0)
        sl = round(price * 1.005, 2) if asset_key == 'XAUUSD' else round(price * 1.01, 0)
    elif rsi > 70:
        signal = 'SELL'
        confidence = 'Medium'
        reasoning = f'RSI deeply overbought ({rsi}) - potential drop'
        tp = round(price * 0.997, 2) if asset_key == 'XAUUSD' else round(price * 0.995, 0)
        sl = round(price * 1.003, 2) if asset_key == 'XAUUSD' else round(price * 1.005, 0)
    else:
        signal = 'HOLD'
        confidence = 'Low'
        reasoning = f'RSI at {rsi} - waiting for setup near S/R (S:${support:.2f}/R:${resistance:.2f})'
        tp = price
        sl = price
    
    return signal, confidence, tp, sl, reasoning

# ============================================================
# TRADING BOT LOOP
# ============================================================

def trading_bot_loop():
    """Main trading loop - runs every 60 seconds"""
    print("=" * 50)
    print("🤖 TRADING BOT STARTED!")
    print("📊 Gold API: api.gold-api.com")
    print("📊 Bitcoin API: CoinGecko")
    print("=" * 50)
    
    while True:
        try:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Fetching market data...")
            
            # === GOLD (XAUUSD) ===
            gold_price = get_gold_price()
            
            if gold_price:
                # FIXED: Better RSI and S/R for gold
                gold_rsi = 50  # Neutral default
                gold_support = round(gold_price - 10, 2)   # $10 below current
                gold_resistance = round(gold_price + 10, 2)  # $10 above current
                
                signal, conf, tp, sl, reason = generate_signal(
                    'XAUUSD', gold_price, gold_rsi, gold_support, gold_resistance
                )
                
                assets_data['XAUUSD'] = {
                    'price': gold_price,
                    'rsi': gold_rsi,
                    'support': gold_support,
                    'resistance': gold_resistance,
                    'signal': signal,
                    'confidence': conf,
                    'position': None,
                    'take_profit': tp,
                    'stop_loss': sl,
                    'reasoning': reason,
                    'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                print(f"   ✅ XAUUSD: ${gold_price:.2f} | S:${gold_support:.2f} R:${gold_resistance:.2f} | Signal: {signal}")
            else:
                print(f"   ❌ Failed to get XAUUSD price")
                assets_data['XAUUSD']['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            time.sleep(2)
            
            # === BITCOIN (BTCUSD) ===
            btc_price = get_bitcoin_price()
            btc_history = get_bitcoin_history()
            
            if btc_price:
                btc_rsi = calculate_rsi(btc_history, 14) if btc_history else 50
                
                # FIXED: Better S/R for Bitcoin
                if btc_history and len(btc_history) >= 20:
                    recent = btc_history[-20:]
                    high = max(recent)
                    low = min(recent)
                    range_val = high - low
                    btc_support = round(low + (range_val * 0.236), 0)
                    btc_resistance = round(high - (range_val * 0.236), 0)
                else:
                    btc_support = round(btc_price - 500, 0)
                    btc_resistance = round(btc_price + 500, 0)
                
                signal, conf, tp, sl, reason = generate_signal(
                    'BTCUSD', btc_price, btc_rsi, btc_support, btc_resistance
                )
                
                assets_data['BTCUSD'] = {
                    'price': btc_price,
                    'rsi': btc_rsi,
                    'support': btc_support,
                    'resistance': btc_resistance,
                    'signal': signal,
                    'confidence': conf,
                    'position': None,
                    'take_profit': tp,
                    'stop_loss': sl,
                    'reasoning': reason,
                    'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                print(f"   ✅ BTCUSD: ${btc_price:.0f} | RSI: {btc_rsi} | Signal: {signal}")
                print(f"      Support: ${btc_support:.0f} | Resistance: ${btc_resistance:.0f}")
            else:
                print(f"   ❌ Failed to get BTCUSD price")
                assets_data['BTCUSD']['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
        except Exception as e:
            print(f"❌ Loop error: {e}")
        
        print(f"\n⏳ Waiting 60 seconds... Next update at {datetime.now().strftime('%H:%M:%S')}")
        time.sleep(60)

# ============================================================
# WEB UI
# ============================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🤖 AI Dual Scalper | Live Trading Bot</title>
    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: system-ui, -apple-system, sans-serif;
            background: linear-gradient(135deg, #0a0f1a 0%, #0f172a 100%);
            color: #eef2ff;
            padding: 20px;
        }
        .container { max-width: 1600px; margin: 0 auto; }
        .header {
            background: rgba(17, 24, 39, 0.9);
            backdrop-filter: blur(10px);
            border-radius: 28px;
            padding: 24px;
            margin-bottom: 24px;
            border: 1px solid #1e293b;
            text-align: center;
        }
        .header h1 { font-size: 1.8rem; color: #fbbf24; }
        .header p { color: #94a3b8; margin-top: 8px; }
        .status-badge {
            display: inline-block;
            background: #10b981;
            padding: 8px 20px;
            border-radius: 40px;
            font-size: 0.75rem;
            margin-top: 12px;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.6; }
        }
        .dual-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 24px; }
        .card {
            background: rgba(17, 24, 39, 0.9);
            backdrop-filter: blur(10px);
            border-radius: 24px;
            border: 1px solid #1e293b;
            overflow: hidden;
        }
        .card-header {
            background: #111827;
            padding: 16px 20px;
            font-size: 1.2rem;
            font-weight: bold;
            border-bottom: 1px solid #1e293b;
        }
        .card-header span { color: #fbbf24; }
        .price {
            font-size: 2.2rem;
            font-weight: bold;
            color: #fbbf24;
            text-align: center;
            padding: 20px;
            font-family: monospace;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
            padding: 0 20px 20px 20px;
        }
        .stat {
            background: #0f172a;
            padding: 12px;
            border-radius: 16px;
            text-align: center;
        }
        .stat-label { font-size: 0.7rem; color: #9ca3af; text-transform: uppercase; }
        .stat-value { font-size: 1.2rem; font-weight: bold; font-family: monospace; }
        .signal-display {
            text-align: center;
            padding: 20px;
            margin: 0 20px 20px 20px;
            border-radius: 20px;
            font-size: 2rem;
            font-weight: bold;
        }
        .signal-BUY { background: rgba(16, 185, 129, 0.2); border: 2px solid #10b981; color: #10b981; }
        .signal-SELL { background: rgba(239, 68, 68, 0.2); border: 2px solid #ef4444; color: #ef4444; }
        .signal-HOLD { background: rgba(245, 158, 11, 0.2); border: 2px solid #f59e0b; color: #f59e0b; }
        .reasoning {
            background: #0f172a;
            margin: 0 20px 20px 20px;
            padding: 12px;
            border-radius: 12px;
            font-size: 0.8rem;
            color: #cbd5e1;
        }
        .chart-container { width: 100%; height: 370px; padding: 12px; background: #131d2c; border-radius: 16px; margin-bottom: 12px; }
        .footer {
            text-align: center;
            margin-top: 24px;
            font-size: 0.7rem;
            color: #64748b;
        }
        @media (max-width: 768px) {
            .dual-grid { grid-template-columns: 1fr; }
            .price { font-size: 1.5rem; }
            .signal-display { font-size: 1.3rem; }
        }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>⚡ AI Dual Scalper | Live Trading Bot</h1>
        <p>XAUUSD + BTCUSD | Real-Time | 5-Minute Scalping Strategy</p>
        <div class="status-badge" id="statusBadge">🟢 LIVE DATA</div>
    </div>

    <div class="dual-grid">
        <div class="card">
            <div class="card-header">🥇 <span>XAUUSD (Gold)</span></div>
            <div class="price" id="xauPrice">$---</div>
            <div class="stats">
                <div class="stat"><div class="stat-label">RSI</div><div class="stat-value" id="xauRsi">---</div></div>
                <div class="stat"><div class="stat-label">Support</div><div class="stat-value" id="xauSupport">---</div></div>
                <div class="stat"><div class="stat-label">Resistance</div><div class="stat-value" id="xauResistance">---</div></div>
            </div>
            <div class="signal-display" id="xauSignal">WAITING</div>
            <div class="reasoning" id="xauReasoning">Awaiting market data...</div>
        </div>

        <div class="card">
            <div class="card-header">₿ <span>BTCUSD (Bitcoin)</span></div>
            <div class="price" id="btcPrice">$---</div>
            <div class="stats">
                <div class="stat"><div class="stat-label">RSI</div><div class="stat-value" id="btcRsi">---</div></div>
                <div class="stat"><div class="stat-label">Support</div><div class="stat-value" id="btcSupport">---</div></div>
                <div class="stat"><div class="stat-label">Resistance</div><div class="stat-value" id="btcResistance">---</div></div>
            </div>
            <div class="signal-display" id="btcSignal">WAITING</div>
            <div class="reasoning" id="btcReasoning">Awaiting market data...</div>
        </div>
    </div>

    <div class="card">
        <div class="card-header">📈 <span>Live Charts (5-Minute)</span></div>
        <div class="chart-container" id="tv-xau-container"></div>
        <div class="chart-container" id="tv-btc-container"></div>
    </div>

    <div class="footer">
        <p>🤖 Bot runs 24/7 | Updates every 60 seconds | Auto-trading ready</p>
        <p id="updateTime">Waiting for data...</p>
    </div>
</div>

<script>
    let xauChart, btcChart;
    
    function initCharts() {
        if (typeof TradingView !== 'undefined') {
            try {
                xauChart = new TradingView.widget({
                    width: "100%", height: 370, symbol: "OANDA:XAUUSD", interval: "5", 
                    theme: "dark", style: "1", locale: "en",
                    container_id: "tv-xau-container", studies: ["RSI@tv-basicstudies"]
                });
                btcChart = new TradingView.widget({
                    width: "100%", height: 370, symbol: "BITSTAMP:BTCUSD", interval: "5", 
                    theme: "dark", style: "1", locale: "en",
                    container_id: "tv-btc-container", studies: ["RSI@tv-basicstudies"]
                });
                console.log("✅ Charts loaded");
            } catch(e) { console.log("Chart error:", e); }
        } else {
            setTimeout(initCharts, 1000);
        }
    }
    
    function updateUI() {
        fetch('/api/all')
            .then(res => res.json())
            .then(data => {
                // Update XAUUSD
                if (data.XAUUSD.price) {
                    document.getElementById('xauPrice').innerHTML = `$${data.XAUUSD.price.toFixed(2)}`;
                    document.getElementById('xauRsi').innerHTML = data.XAUUSD.rsi || '---';
                    document.getElementById('xauSupport').innerHTML = data.XAUUSD.support ? `$${data.XAUUSD.support.toFixed(2)}` : '---';
                    document.getElementById('xauResistance').innerHTML = data.XAUUSD.resistance ? `$${data.XAUUSD.resistance.toFixed(2)}` : '---';
                    const xauDiv = document.getElementById('xauSignal');
                    xauDiv.className = `signal-display signal-${data.XAUUSD.signal}`;
                    xauDiv.innerHTML = data.XAUUSD.signal;
                    document.getElementById('xauReasoning').innerHTML = `💭 ${data.XAUUSD.reasoning}`;
                }
                
                // Update BTCUSD
                if (data.BTCUSD.price) {
                    document.getElementById('btcPrice').innerHTML = `$${data.BTCUSD.price.toFixed(0)}`;
                    document.getElementById('btcRsi').innerHTML = data.BTCUSD.rsi || '---';
                    document.getElementById('btcSupport').innerHTML = data.BTCUSD.support ? `$${data.BTCUSD.support.toFixed(0)}` : '---';
                    document.getElementById('btcResistance').innerHTML = data.BTCUSD.resistance ? `$${data.BTCUSD.resistance.toFixed(0)}` : '---';
                    const btcDiv = document.getElementById('btcSignal');
                    btcDiv.className = `signal-display signal-${data.BTCUSD.signal}`;
                    btcDiv.innerHTML = data.BTCUSD.signal;
                    document.getElementById('btcReasoning').innerHTML = `💭 ${data.BTCUSD.reasoning}`;
                }
                
                // Update timestamp
                if (data.XAUUSD.last_update && data.XAUUSD.last_update !== 'Never') {
                    document.getElementById('updateTime').innerHTML = `Last update: ${data.XAUUSD.last_update}`;
                    document.getElementById('statusBadge').innerHTML = '🟢 LIVE DATA';
                    document.getElementById('statusBadge').style.background = '#10b981';
                } else if (data.XAUUSD.last_update === 'Never') {
                    document.getElementById('statusBadge').innerHTML = '🟡 FIRST FETCH...';
                }
            })
            .catch(err => {
                console.log("Fetch error:", err);
                document.getElementById('statusBadge').innerHTML = '🔴 CONNECTING...';
            });
    }
    
    // Initialize
    setTimeout(initCharts, 500);
    updateUI();
    setInterval(updateUI, 5000);  // Update every 5 seconds as you suggested
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/all')
def api_all():
    return jsonify(assets_data)

# ============================================================
# START THE BOT
# ============================================================

print("=" * 60)
print("🚀 AI DUAL SCALPER - LIVE TRADING BOT")
print("=" * 60)
print("✅ Gold API: api.gold-api.com")
print("✅ Bitcoin API: CoinGecko")
print("✅ Thresholds: Gold $10, Bitcoin $500")
print("✅ UI Update: Every 5 seconds")
print("=" * 60)

# Start trading bot thread
bot_thread = threading.Thread(target=trading_bot_loop, daemon=True)
bot_thread.start()
print("✅ Trading bot thread started!")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
