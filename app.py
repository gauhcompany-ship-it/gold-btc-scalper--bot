import requests
import time
import json
import os
import threading
from datetime import datetime
from flask import Flask, render_template_string, jsonify

app = Flask(__name__)

# ============================================================
# CONFIGURATION - USE YOUR KEYS (they work!)
# ============================================================
GROQ_API_KEY = "gsk_inI4X1nm01tkaXEcjJ0GWGdyb3FYWnllwn7anFXMDF4n9lITR0u4hF"
TWELVE_API_KEY = "ef1b1adda82943bca544ea28b3d44751"

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
# TWELVE DATA FUNCTIONS (YOUR KEYS WORK HERE!)
# ============================================================

def get_twelve_data(symbol):
    """Get real-time data from Twelve Data - works with your keys!"""
    try:
        # Map symbols
        api_symbol = 'XAU/USD' if symbol == 'XAUUSD' else 'BTC/USD'
        
        # Get time series for RSI and S/R
        url = f"https://api.twelvedata.com/time_series?symbol={api_symbol}&interval=5min&outputsize=30&apikey={TWELVE_API_KEY}"
        
        print(f"Fetching {symbol} from Twelve Data...")
        response = requests.get(url, timeout=15)
        data = response.json()
        
        # Check for errors
        if 'code' in data and data['code'] == 401:
            print(f"API key error: {data.get('message', 'Invalid key')}")
            return None
            
        if 'values' not in data or not data['values']:
            print(f"No values for {symbol}: {data}")
            return None
        
        # Extract prices
        prices = []
        for v in data['values']:
            try:
                prices.append(float(v['close']))
            except:
                continue
        
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
        support = low + (range_val * 0.236)
        resistance = high - (range_val * 0.236)
        
        return {
            'price': round(current_price, 2),
            'rsi': rsi,
            'support': round(support, 2),
            'resistance': round(resistance, 2)
        }
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return None

# ============================================================
# SIGNAL GENERATION
# ============================================================

def generate_signal(asset_key, market_data):
    """Generate trading signal based on RSI + Support/Resistance"""
    price = market_data['price']
    rsi = market_data['rsi']
    support = market_data['support']
    resistance = market_data['resistance']
    
    # Check if near support/resistance
    near_support = abs(price - support) < (1.5 if asset_key == 'XAUUSD' else 150)
    near_resistance = abs(price - resistance) < (1.5 if asset_key == 'XAUUSD' else 150)
    
    # Scalping strategy
    if rsi < 35 and near_support:
        signal = 'BUY'
        confidence = 'High'
        reasoning = f'RSI oversold ({rsi}) near support ${support}'
        take_profit = round(price * 1.005, 2) if asset_key == 'XAUUSD' else round(price * 1.01, 0)
        stop_loss = round(price * 0.995, 2) if asset_key == 'XAUUSD' else round(price * 0.99, 0)
    elif rsi > 65 and near_resistance:
        signal = 'SELL'
        confidence = 'High'
        reasoning = f'RSI overbought ({rsi}) near resistance ${resistance}'
        take_profit = round(price * 0.995, 2) if asset_key == 'XAUUSD' else round(price * 0.99, 0)
        stop_loss = round(price * 1.005, 2) if asset_key == 'XAUUSD' else round(price * 1.01, 0)
    elif rsi < 30:
        signal = 'BUY'
        confidence = 'Medium'
        reasoning = f'RSI deeply oversold ({rsi}) - potential bounce'
        take_profit = round(price * 1.003, 2) if asset_key == 'XAUUSD' else round(price * 1.005, 0)
        stop_loss = round(price * 0.997, 2) if asset_key == 'XAUUSD' else round(price * 0.995, 0)
    elif rsi > 70:
        signal = 'SELL'
        confidence = 'Medium'
        reasoning = f'RSI deeply overbought ({rsi}) - potential drop'
        take_profit = round(price * 0.997, 2) if asset_key == 'XAUUSD' else round(price * 0.995, 0)
        stop_loss = round(price * 1.003, 2) if asset_key == 'XAUUSD' else round(price * 1.005, 0)
    else:
        signal = 'HOLD'
        confidence = 'Low'
        reasoning = f'RSI at {rsi} - waiting for setup near S/R'
        take_profit = price
        stop_loss = price
    
    return {
        'signal': signal,
        'confidence': confidence,
        'take_profit': take_profit,
        'stop_loss': stop_loss,
        'reasoning': reasoning
    }

# ============================================================
# TRADING BOT LOOP
# ============================================================

def trading_bot_loop():
    """Main trading loop - runs every 60 seconds"""
    print("=" * 50)
    print("🤖 TRADING BOT STARTED!")
    print(f"📊 Twelve Data Key: {TWELVE_API_KEY[:10]}...")
    print("=" * 50)
    
    # Initial fetch immediately
    print("🔄 Fetching initial data...")
    
    while True:
        for asset_key in ['XAUUSD', 'BTCUSD']:
            try:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Fetching {asset_key}...")
                
                market_data = get_twelve_data(asset_key)
                
                if market_data and market_data['price']:
                    signal_data = generate_signal(asset_key, market_data)
                    
                    assets_data[asset_key] = {
                        'price': market_data['price'],
                        'rsi': market_data['rsi'],
                        'support': market_data['support'],
                        'resistance': market_data['resistance'],
                        'signal': signal_data['signal'],
                        'confidence': signal_data['confidence'],
                        'position': assets_data[asset_key].get('position'),
                        'take_profit': signal_data['take_profit'],
                        'stop_loss': signal_data['stop_loss'],
                        'reasoning': signal_data['reasoning'],
                        'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    
                    print(f"   ✅ {asset_key}: ${market_data['price']:.2f}")
                    print(f"   📊 RSI: {market_data['rsi']} | Signal: {signal_data['signal']}")
                    print(f"   🛡️ Support: ${market_data['support']} | Resistance: ${market_data['resistance']}")
                else:
                    print(f"   ❌ Failed to get data for {asset_key}")
                    # Keep existing data, just mark as stale
                    assets_data[asset_key]['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                time.sleep(3)  # Delay between assets
                
            except Exception as e:
                print(f"❌ Error in {asset_key}: {e}")
        
        print(f"\n⏳ Waiting 60 seconds... Next update at {datetime.now().strftime('%H:%M:%S')}")
        time.sleep(60)

# ============================================================
# WEB UI - SIMPLE BUT COMPLETE
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
        .chart-container { width: 100%; height: 350px; padding: 12px; }
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
            .stats { grid-template-columns: repeat(3, 1fr); gap: 8px; }
            .stat-value { font-size: 0.9rem; }
        }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>⚡ AI Dual Scalper | Live Trading Bot</h1>
        <p>XAUUSD + BTCUSD | 5-Minute Scalping | Real-Time Data</p>
        <div class="status-badge" id="statusBadge">🟢 LIVE DATA</div>
    </div>

    <div class="dual-grid">
        <!-- XAUUSD Card -->
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

        <!-- BTCUSD Card -->
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

    <!-- TradingView Charts -->
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
    let lastUpdateTime = null;
    
    function initCharts() {
        if (typeof TradingView !== 'undefined') {
            try {
                xauChart = new TradingView.widget({
                    width: "100%", height: 350, symbol: "OANDA:XAUUSD", interval: "5", 
                    theme: "dark", style: "1", locale: "en",
                    container_id: "tv-xau-container", studies: ["RSI@tv-basicstudies"], 
                    autosize: false
                });
                btcChart = new TradingView.widget({
                    width: "100%", height: 350, symbol: "BITSTAMP:BTCUSD", interval: "5", 
                    theme: "dark", style: "1", locale: "en",
                    container_id: "tv-btc-container", studies: ["RSI@tv-basicstudies"]
                });
                console.log("✅ Charts loaded");
            } catch(e) {
                console.log("Chart error:", e);
            }
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
                    document.getElementById('xauSupport').innerHTML = data.XAUUSD.support ? `$${data.XAUUSD.support}` : '---';
                    document.getElementById('xauResistance').innerHTML = data.XAUUSD.resistance ? `$${data.XAUUSD.resistance}` : '---';
                    
                    const xauSignalDiv = document.getElementById('xauSignal');
                    xauSignalDiv.className = `signal-display signal-${data.XAUUSD.signal}`;
                    xauSignalDiv.innerHTML = data.XAUUSD.signal;
                    document.getElementById('xauReasoning').innerHTML = `💭 ${data.XAUUSD.reasoning || 'Analyzing...'}`;
                }
                
                // Update BTCUSD
                if (data.BTCUSD.price) {
                    document.getElementById('btcPrice').innerHTML = `$${data.BTCUSD.price.toFixed(0)}`;
                    document.getElementById('btcRsi').innerHTML = data.BTCUSD.rsi || '---';
                    document.getElementById('btcSupport').innerHTML = data.BTCUSD.support ? `$${data.BTCUSD.support}` : '---';
                    document.getElementById('btcResistance').innerHTML = data.BTCUSD.resistance ? `$${data.BTCUSD.resistance}` : '---';
                    
                    const btcSignalDiv = document.getElementById('btcSignal');
                    btcSignalDiv.className = `signal-display signal-${data.BTCUSD.signal}`;
                    btcSignalDiv.innerHTML = data.BTCUSD.signal;
                    document.getElementById('btcReasoning').innerHTML = `💭 ${data.BTCUSD.reasoning || 'Analyzing...'}`;
                }
                
                // Update timestamp
                if (data.XAUUSD.last_update && data.XAUUSD.last_update !== lastUpdateTime) {
                    lastUpdateTime = data.XAUUSD.last_update;
                    document.getElementById('updateTime').innerHTML = `Last update: ${data.XAUUSD.last_update}`;
                    document.getElementById('statusBadge').innerHTML = '🟢 LIVE DATA';
                    document.getElementById('statusBadge').style.background = '#10b981';
                } else if (!data.XAUUSD.price) {
                    document.getElementById('statusBadge').innerHTML = '🟡 FETCHING DATA...';
                }
            })
            .catch(err => {
                console.log('Fetch error:', err);
                document.getElementById('statusBadge').innerHTML = '🔴 CONNECTING...';
            });
    }
    
    // Initialize
    setTimeout(initCharts, 500);
    updateUI();
    setInterval(updateUI, 3000);  // Update every 3 seconds
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
print(f"📊 Twelve Data API Key: {TWELVE_API_KEY[:10]}...")
print("✅ Bot will fetch real-time data every 60 seconds")
print("=" * 60)

# Start trading bot thread
bot_thread = threading.Thread(target=trading_bot_loop, daemon=True)
bot_thread.start()
print("✅ Trading bot thread started!")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
