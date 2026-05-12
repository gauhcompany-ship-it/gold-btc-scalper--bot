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
GROQ_API_KEY = "gsk_inI4X1nm01tkaXEcjJ0GWGdyb3FYWnllwn7anFXMDF4n9lITR0u4hF"
TWELVE_API_KEY = "9663744f36eb47da84d6ddd016afaaace"

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
# SIMPLE MARKET DATA FUNCTIONS
# ============================================================

def get_single_price(symbol):
    """Get current price only - simpler API call"""
    try:
        api_symbol = 'XAU/USD' if symbol == 'XAUUSD' else 'BTC/USD'
        url = f"https://api.twelvedata.com/price?symbol={api_symbol}&apikey={TWELVE_API_KEY}"
        print(f"Fetching {symbol} from: {url}")
        
        response = requests.get(url, timeout=10)
        data = response.json()
        
        print(f"Response for {symbol}: {data}")
        
        if 'price' in data:
            return float(data['price'])
        else:
            print(f"Error for {symbol}: {data.get('message', 'Unknown error')}")
            return None
    except Exception as e:
        print(f"Price error for {symbol}: {e}")
        return None

def get_full_market_data(symbol):
    """Get time series for RSI calculation"""
    try:
        api_symbol = 'XAU/USD' if symbol == 'XAUUSD' else 'BTC/USD'
        url = f"https://api.twelvedata.com/time_series?symbol={api_symbol}&interval=5min&outputsize=30&apikey={TWELVE_API_KEY}"
        
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if 'values' not in data or not data['values']:
            print(f"No time series for {symbol}")
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
        
        # Calculate support/resistance (simple version)
        recent = prices[-20:]
        high = max(recent)
        low = min(recent)
        range_val = high - low
        support = round(low + (range_val * 0.236), 2)
        resistance = round(high - (range_val * 0.236), 2)
        
        return {
            'price': current_price,
            'rsi': rsi,
            'support': support,
            'resistance': resistance,
            'prices': prices
        }
    except Exception as e:
        print(f"Market data error for {symbol}: {e}")
        return None

# ============================================================
# SIMPLE AI SIGNAL
# ============================================================

def get_ai_signal(asset_key, market_data):
    """Get trading signal from Groq AI"""
    price = market_data['price']
    rsi = market_data['rsi']
    support = market_data['support']
    resistance = market_data['resistance']
    
    # Simple rule-based logic first
    signal = 'HOLD'
    reasoning = ''
    
    if rsi < 35 and price <= support * 1.005:
        signal = 'BUY'
        reasoning = f'RSI oversold ({rsi}) and price near support (${support})'
    elif rsi > 65 and price >= resistance * 0.995:
        signal = 'SELL'
        reasoning = f'RSI overbought ({rsi}) and price near resistance (${resistance})'
    else:
        reasoning = f'RSI at {rsi} - waiting for setup near support/resistance'
    
    # Try Groq for better analysis
    if GROQ_API_KEY and GROQ_API_KEY != "gsk_":
        try:
            prompt = f"""XAUUSD price: ${price}, RSI: {rsi}, Support: ${support}, Resistance: ${resistance}. 
            Reply with JSON only: {{"signal":"BUY/SELL/HOLD", "reason":"short"}}"""
            
            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            }
            data = {
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 100
            }
            
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                import re
                json_match = re.search(r'\{.*\}', content)
                if json_match:
                    groq_result = json.loads(json_match.group())
                    if groq_result.get('signal') in ['BUY', 'SELL', 'HOLD']:
                        signal = groq_result.get('signal')
                        reasoning = groq_result.get('reason', reasoning)
        except Exception as e:
            print(f"Groq error: {e}")
    
    # Set TP/SL based on signal
    if signal == 'BUY':
        tp = price * (1.005 if asset_key == 'XAUUSD' else 1.01)
        sl = price * (0.995 if asset_key == 'XAUUSD' else 0.99)
    elif signal == 'SELL':
        tp = price * (0.995 if asset_key == 'XAUUSD' else 0.99)
        sl = price * (1.005 if asset_key == 'XAUUSD' else 1.01)
    else:
        tp = price
        sl = price
    
    return {
        'signal': signal,
        'confidence': 'Medium',
        'take_profit': round(tp, 2),
        'stop_loss': round(sl, 2),
        'reasoning': reasoning
    }

# ============================================================
# TRADING BOT LOOP
# ============================================================

def trading_bot_loop():
    """Main trading loop"""
    print("=" * 50)
    print("🤖 Trading Bot Started!")
    print("=" * 50)
    print(f"Twelve Data Key: {TWELVE_API_KEY[:10]}...")
    print(f"Groq Key: {GROQ_API_KEY[:15]}...")
    print("=" * 50)
    
    while True:
        for asset_key in ['XAUUSD', 'BTCUSD']:
            try:
                print(f"\n--- Fetching {asset_key} at {datetime.now().strftime('%H:%M:%S')} ---")
                
                # Get market data
                market_data = get_full_market_data(asset_key)
                
                if market_data and market_data['price']:
                    current_price = market_data['price']
                    print(f"✅ {asset_key} Price: ${current_price:.2f}")
                    print(f"   RSI: {market_data['rsi']}, Support: ${market_data['support']}, Resistance: ${market_data['resistance']}")
                    
                    # Get AI signal
                    analysis = get_ai_signal(asset_key, market_data)
                    print(f"   Signal: {analysis['signal']} - {analysis['reasoning']}")
                    
                    # Update global data
                    assets_data[asset_key] = {
                        'price': current_price,
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
                else:
                    print(f"❌ No market data for {asset_key}")
                    assets_data[asset_key]['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                time.sleep(3)  # Small delay between assets
                
            except Exception as e:
                print(f"Error in {asset_key} loop: {e}")
        
        # Wait 60 seconds before next cycle
        print(f"\n⏳ Waiting 60 seconds... Next update at {datetime.now().strftime('%H:%M:%S')}")
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
        <p>XAUUSD + BTCUSD | Real Market Data | Groq AI Analysis | 5-Min Timeframe</p>
    </div>

    <div class="dual-grid">
        <!-- XAUUSD -->
        <div class="card">
            <h2>🥇 XAUUSD (Gold)</h2>
            <div class="price">${{ "%.2f"|format(xau.price) if xau.price else '---' }}</div>
            <div class="stats">
                <div class="stat"><div class="stat-label">RSI (14)</div><div class="stat-value">{{ xau.rsi if xau.rsi else '---' }}</div></div>
                <div class="stat"><div class="stat-label">Support</div><div class="stat-value">${{ "%.2f"|format(xau.support) if xau.support else '---' }}</div></div>
                <div class="stat"><div class="stat-label">Resistance</div><div class="stat-value">${{ "%.2f"|format(xau.resistance) if xau.resistance else '---' }}</div></div>
                <div class="stat"><div class="stat-label">Signal</div><div class="stat-value">{{ xau.signal }}</div></div>
            </div>
            <div class="signal signal-{{ xau.signal }}">{{ xau.signal }}</div>
            <div class="reasoning">💭 {{ xau.reasoning }}</div>
        </div>

        <!-- BTCUSD -->
        <div class="card">
            <h2>₿ BTCUSD (Bitcoin)</h2>
            <div class="price">${{ "%.0f"|format(btc.price) if btc.price else '---' }}</div>
            <div class="stats">
                <div class="stat"><div class="stat-label">RSI (14)</div><div class="stat-value">{{ btc.rsi if btc.rsi else '---' }}</div></div>
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
# MAIN ENTRY POINT - THIS MUST BE AT THE BOTTOM
# ============================================================

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 AI Dual Scalper Starting...")
    print("=" * 50)
    
    # Start trading bot in background thread
    bot_thread = threading.Thread(target=trading_bot_loop, daemon=True)
    bot_thread.start()
    print("✅ Trading bot thread started!")
    
    # Start web server
    port = int(os.environ.get('PORT', 5000))
    print(f"🌐 Web dashboard on port {port}")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=port)
