import requests
import time
import json
import os
import threading
from datetime import datetime
from flask import Flask, render_template_string, jsonify

app = Flask(__name__)

# ============================================================
# CONFIGURATION - PUT YOUR API KEYS DIRECTLY HERE
# ============================================================
GROQ_API_KEY = "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"
TWELVE_API_KEY = "4e1b31d1604d4d42b9e6434b6fbf0b2f"

# Global data storage
assets_data = {
    'XAUUSD': {
        'price': None,
        'rsi': None,
        'support': None,
        'resistance': None,
        'signal': 'WAITING',
        'confidence': 'Low',
        'position': None,
        'take_profit': None,
        'stop_loss': None,
        'reasoning': 'Awaiting first analysis...',
        'last_update': 'Never'
    },
    'BTCUSD': {
        'price': None,
        'rsi': None,
        'support': None,
        'resistance': None,
        'signal': 'WAITING',
        'confidence': 'Low',
        'position': None,
        'take_profit': None,
        'stop_loss': None,
        'reasoning': 'Awaiting first analysis...',
        'last_update': 'Never'
    }
}

# ============================================================
# MARKET DATA FUNCTIONS
# ============================================================

def get_full_market_data(symbol):
    """Get time series for RSI calculation"""
    try:
        api_symbol = 'XAU/USD' if symbol == 'XAUUSD' else 'BTC/USD'
        url = f"https://api.twelvedata.com/time_series?symbol={api_symbol}&interval=5min&outputsize=30&apikey={TWELVE_API_KEY}"
        
        print(f"Fetching {symbol} data...")
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if 'values' not in data or not data['values']:
            print(f"No time series for {symbol}: {data}")
            return None
        
        prices = [float(v['close']) for v in data['values']]
        
        if not prices:
            return None
            
        current_price = prices[-1]
        
        # Calculate RSI
        rsi = 50
        if len(prices) >= 15:
            gains = 0
            losses = 0
            for i in range(len(prices)-15, len(prices)-1):
                diff = prices[i+1] - prices[i]
                if diff >= 0:
                    gains += diff
                else:
                    losses -= diff
            avg_gain = gains / 14
            avg_loss = losses / 14
            if avg_loss > 0:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
                rsi = round(rsi, 1)
        
        # Calculate support/resistance
        recent = prices[-20:]
        high = max(recent)
        low = min(recent)
        range_val = high - low
        support = round(low + (range_val * 0.236), 2)
        resistance = round(high - (range_val * 0.236), 2)
        
        print(f"✅ {symbol}: ${current_price:.2f}, RSI: {rsi}")
        
        return {
            'price': current_price,
            'rsi': rsi,
            'support': support,
            'resistance': resistance
        }
    except Exception as e:
        print(f"Market data error for {symbol}: {e}")
        return None

def get_ai_signal(asset_key, market_data):
    """Get trading signal"""
    price = market_data['price']
    rsi = market_data['rsi']
    support = market_data['support']
    resistance = market_data['resistance']
    
    # Simple rule-based logic
    if rsi < 35 and price <= support * 1.005:
        signal = 'BUY'
        reasoning = f'RSI oversold ({rsi}) near support (${support})'
    elif rsi > 65 and price >= resistance * 0.995:
        signal = 'SELL'
        reasoning = f'RSI overbought ({rsi}) near resistance (${resistance})'
    else:
        signal = 'HOLD'
        reasoning = f'RSI at {rsi} - no clear signal'
    
    # Set TP/SL
    if signal == 'BUY':
        tp = round(price * (1.005 if asset_key == 'XAUUSD' else 1.01), 2)
        sl = round(price * (0.995 if asset_key == 'XAUUSD' else 0.99), 2)
    elif signal == 'SELL':
        tp = round(price * (0.995 if asset_key == 'XAUUSD' else 0.99), 2)
        sl = round(price * (1.005 if asset_key == 'XAUUSD' else 1.01), 2)
    else:
        tp = price
        sl = price
    
    return {
        'signal': signal,
        'confidence': 'Medium',
        'take_profit': tp,
        'stop_loss': sl,
        'reasoning': reasoning
    }

# ============================================================
# TRADING BOT LOOP
# ============================================================

def trading_bot_loop():
    """Main trading loop - runs in background"""
    print("=" * 50)
    print("🤖 TRADING BOT STARTED!")
    print("=" * 50)
    print(f"Twelve Data Key: {TWELVE_API_KEY[:10]}...")
    print(f"Groq Key: {GROQ_API_KEY[:15]}...")
    print("=" * 50)
    
    while True:
        for asset_key in ['XAUUSD', 'BTCUSD']:
            try:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Fetching {asset_key}...")
                
                market_data = get_full_market_data(asset_key)
                
                if market_data and market_data['price']:
                    analysis = get_ai_signal(asset_key, market_data)
                    
                    assets_data[asset_key] = {
                        'price': market_data['price'],
                        'rsi': market_data['rsi'],
                        'support': market_data['support'],
                        'resistance': market_data['resistance'],
                        'signal': analysis['signal'],
                        'confidence': analysis['confidence'],
                        'position': assets_data[asset_key].get('position'),
                        'take_profit': analysis['take_profit'],
                        'stop_loss': analysis['stop_loss'],
                        'reasoning': analysis['reasoning'],
                        'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    
                    print(f"   Price: ${market_data['price']:.2f} | Signal: {analysis['signal']}")
                else:
                    print(f"   ❌ No data for {asset_key}")
                
                time.sleep(3)
                
            except Exception as e:
                print(f"Error in {asset_key}: {e}")
        
        print(f"\n⏳ Waiting 60 seconds...")
        time.sleep(60)

# ============================================================
# WEB DASHBOARD
# ============================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🤖 AI Dual Scalper</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: system-ui, -apple-system, sans-serif;
            background: linear-gradient(135deg, #0a0f1a 0%, #0f172a 100%);
            color: #eef2ff;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        .header {
            background: rgba(17, 24, 39, 0.8);
            border-radius: 28px;
            padding: 20px;
            margin-bottom: 24px;
            border: 1px solid #1e293b;
            text-align: center;
        }
        .header h1 { font-size: 1.5rem; color: #fbbf24; }
        .dual-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
        .card {
            background: rgba(17, 24, 39, 0.8);
            border-radius: 24px;
            padding: 20px;
            border: 1px solid #1e293b;
        }
        .card h2 { color: #fbbf24; margin-bottom: 16px; }
        .price { font-size: 2.5rem; font-weight: bold; font-family: monospace; color: #fbbf24; }
        .stats { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 16px 0; }
        .stat { background: #0f172a; padding: 10px; border-radius: 12px; text-align: center; }
        .stat-label { font-size: 0.7rem; color: #9ca3af; }
        .stat-value { font-size: 1.2rem; font-weight: bold; }
        .signal {
            text-align: center;
            padding: 16px;
            border-radius: 16px;
            margin: 16px 0;
            font-size: 1.8rem;
            font-weight: bold;
        }
        .signal-BUY { background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981; color: #10b981; }
        .signal-SELL { background: rgba(239, 68, 68, 0.2); border: 1px solid #ef4444; color: #ef4444; }
        .signal-HOLD { background: rgba(245, 158, 11, 0.2); border: 1px solid #f59e0b; color: #f59e0b; }
        .reasoning { font-size: 0.8rem; color: #cbd5e1; margin-top: 12px; padding-top: 12px; border-top: 1px solid #1e293b; }
        .footer { text-align: center; margin-top: 24px; font-size: 0.7rem; color: #64748b; }
        @media (max-width: 768px) { .dual-grid { grid-template-columns: 1fr; } .price { font-size: 1.8rem; } }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>⚡ AI Dual Scalper</h1>
        <p>XAUUSD + BTCUSD | Real Market Data | 5-Min Timeframe</p>
    </div>

    <div class="dual-grid">
        <div class="card">
            <h2>🥇 XAUUSD (Gold)</h2>
            <div class="price">${{ "%.2f"|format(xau.price) if xau.price else '---' }}</div>
            <div class="stats">
                <div class="stat"><div class="stat-label">RSI</div><div class="stat-value">{{ xau.rsi if xau.rsi else '---' }}</div></div>
                <div class="stat"><div class="stat-label">Support</div><div class="stat-value">${{ "%.2f"|format(xau.support) if xau.support else '---' }}</div></div>
                <div class="stat"><div class="stat-label">Resistance</div><div class="stat-value">${{ "%.2f"|format(xau.resistance) if xau.resistance else '---' }}</div></div>
                <div class="stat"><div class="stat-label">Signal</div><div class="stat-value">{{ xau.signal }}</div></div>
            </div>
            <div class="signal signal-{{ xau.signal }}">{{ xau.signal }}</div>
            <div class="reasoning">💭 {{ xau.reasoning }}</div>
        </div>

        <div class="card">
            <h2>₿ BTCUSD (Bitcoin)</h2>
            <div class="price">${{ "%.0f"|format(btc.price) if btc.price else '---' }}</div>
            <div class="stats">
                <div class="stat"><div class="stat-label">RSI</div><div class="stat-value">{{ btc.rsi if btc.rsi else '---' }}</div></div>
                <div class="stat"><div class="stat-label">Support</div><div class="stat-value">${{ "%.0f"|format(btc.support) if btc.support else '---' }}</div></div>
                <div class="stat"><div class="stat-label">Resistance</div><div class="stat-value">${{ "%.0f"|format(btc.resistance) if btc.resistance else '---' }}</div></div>
                <div class="stat"><div class="stat-label">Signal</div><div class="stat-value">{{ btc.signal }}</div></div>
            </div>
            <div class="signal signal-{{ btc.signal }}">{{ btc.signal }}</div>
            <div class="reasoning">💭 {{ btc.reasoning }}</div>
        </div>
    </div>

    <div class="footer">
        Last update: {{ xau.last_update if xau.last_update else 'Waiting for data...' }}
    </div>
</div>
<script>
    setInterval(function() { location.reload(); }, 10000);
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, 
                                  xau=assets_data['XAUUSD'], 
                                  btc=assets_data['BTCUSD'])

@app.route('/api/all')
def api_all():
    return jsonify(assets_data)

# ============================================================
# START THE BOT THREAD WHEN APP INITIALIZES
# ============================================================

print("🚀 Starting AI Dual Scalper...")
print("   Initializing trading bot thread...")

# Start trading bot in background thread
bot_thread = threading.Thread(target=trading_bot_loop, daemon=True)
bot_thread.start()
print("✅ Trading bot thread started!")

print("   Web server will start shortly...")
print("=" * 50)

# ============================================================
# RUN THE APP (for local testing)
# ============================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
