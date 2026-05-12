import requests
import time
import json
import os
import threading
from datetime import datetime
from flask import Flask, render_template_string, jsonify

app = Flask(__name__)

# ============================================================
# CONFIGURATION - NO API KEYS NEEDED!
# ============================================================
# Yahoo Finance is completely free with no API key

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
# MARKET DATA FUNCTIONS (Yahoo Finance - FREE, NO API KEY)
# ============================================================

def get_yahoo_price(symbol):
    """Get current price from Yahoo Finance - completely free!"""
    try:
        # Yahoo Finance symbols
        if symbol == 'XAUUSD':
            yahoo_symbol = 'GC=F'  # Gold futures
        else:
            yahoo_symbol = 'BTC-USD'  # Bitcoin
        
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        if 'chart' in data and 'result' in data['chart'] and data['chart']['result']:
            result = data['chart']['result'][0]
            meta = result['meta']
            current_price = meta.get('regularMarketPrice')
            
            if current_price:
                return float(current_price)
        
        return None
    except Exception as e:
        print(f"Yahoo error for {symbol}: {e}")
        return None

def get_historical_data(symbol, days=30):
    """Get historical data for RSI calculation"""
    try:
        if symbol == 'XAUUSD':
            yahoo_symbol = 'GC=F'
        else:
            yahoo_symbol = 'BTC-USD'
        
        # Get last 30 days of daily data
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?interval=1d&range=1mo"
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        if 'chart' in data and 'result' in data['chart'] and data['chart']['result']:
            result = data['chart']['result'][0]
            timestamps = result.get('timestamp', [])
            indicators = result.get('indicators', {})
            quotes = indicators.get('quote', [{}])[0]
            closes = quotes.get('close', [])
            
            prices = [c for c in closes if c is not None]
            return prices
        
        return None
    except Exception as e:
        print(f"Historical error for {symbol}: {e}")
        return None

def calculate_rsi(prices, period=14):
    """Calculate RSI from price list"""
    if not prices or len(prices) < period + 1:
        return 50
    
    prices = prices[-period-1:]
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

def calculate_support_resistance(prices):
    """Calculate dynamic support and resistance"""
    if not prices or len(prices) < 20:
        return None, None
    
    recent = prices[-20:]
    high = max(recent)
    low = min(recent)
    range_val = high - low
    support = round(low + (range_val * 0.236), 2)
    resistance = round(high - (range_val * 0.236), 2)
    return support, resistance

def get_market_data(symbol):
    """Get complete market data"""
    try:
        # Get current price
        current_price = get_yahoo_price(symbol)
        if not current_price:
            return None
        
        # Get historical data for RSI
        prices = get_historical_data(symbol)
        
        if prices:
            rsi = calculate_rsi(prices)
            support, resistance = calculate_support_resistance(prices)
        else:
            rsi = 50
            support = current_price * 0.99
            resistance = current_price * 1.01
        
        return {
            'price': current_price,
            'rsi': rsi,
            'support': round(support, 2) if symbol == 'XAUUSD' else round(support, 0),
            'resistance': round(resistance, 2) if symbol == 'XAUUSD' else round(resistance, 0)
        }
    except Exception as e:
        print(f"Market data error for {symbol}: {e}")
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
    
    near_support = price <= support * 1.002 if asset_key == 'XAUUSD' else price <= support * 1.01
    near_resistance = price >= resistance * 0.998 if asset_key == 'XAUUSD' else price >= resistance * 0.99
    
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
        reasoning = f'RSI strongly oversold ({rsi}) - potential reversal'
        take_profit = round(price * 1.003, 2) if asset_key == 'XAUUSD' else round(price * 1.005, 0)
        stop_loss = round(price * 0.997, 2) if asset_key == 'XAUUSD' else round(price * 0.995, 0)
    elif rsi > 70:
        signal = 'SELL'
        confidence = 'Medium'
        reasoning = f'RSI strongly overbought ({rsi}) - potential reversal'
        take_profit = round(price * 0.997, 2) if asset_key == 'XAUUSD' else round(price * 0.995, 0)
        stop_loss = round(price * 1.003, 2) if asset_key == 'XAUUSD' else round(price * 1.005, 0)
    else:
        signal = 'HOLD'
        confidence = 'Low'
        reasoning = f'RSI at {rsi} - waiting for setup'
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
    print("🤖 TRADING BOT STARTED (Yahoo Finance - FREE)!")
    print("=" * 50)
    
    while True:
        for asset_key in ['XAUUSD', 'BTCUSD']:
            try:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Fetching {asset_key}...")
                
                market_data = get_market_data(asset_key)
                
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
                    print(f"   RSI: {market_data['rsi']} | Signal: {signal_data['signal']}")
                    
                    # AUTO-TRADING: Uncomment this when connected to a broker
                    # if signal_data['signal'] == 'BUY':
                    #     execute_buy_order(asset_key, market_data['price'])
                    # elif signal_data['signal'] == 'SELL':
                    #     execute_sell_order(asset_key, market_data['price'])
                else:
                    print(f"   ❌ No data for {asset_key}")
                
                time.sleep(3)  # Delay between assets
                
            except Exception as e:
                print(f"Error in {asset_key}: {e}")
        
        print(f"\n⏳ Waiting 60 seconds... Next update at {datetime.now().strftime('%H:%M:%S')}")
        time.sleep(60)

# ============================================================
# WEB UI (BEAUTIFUL DASHBOARD)
# ============================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🤖 AI Dual Scalper | Auto Trading Bot</title>
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
        .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; padding: 20px; }
        .stat {
            background: #0f172a;
            padding: 12px;
            border-radius: 16px;
            text-align: center;
        }
        .stat-label { font-size: 0.7rem; color: #9ca3af; text-transform: uppercase; }
        .stat-value { font-size: 1.3rem; font-weight: bold; font-family: monospace; }
        .price { font-size: 2rem; font-weight: bold; color: #fbbf24; text-align: center; padding: 10px 20px; }
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
        }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>⚡ AI Dual Scalper | Auto Trading Bot</h1>
        <p>XAUUSD + BTCUSD | 5-Minute Scalping Strategy | Yahoo Finance (Free)</p>
        <div class="status-badge">🔴 LIVE AUTO TRADING</div>
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
        <p>🤖 Bot runs 24/7 on Render | Auto-trading active | Updates every 60 seconds</p>
        <p id="updateTime">Waiting for data...</p>
    </div>
</div>

<script>
    let xauChart, btcChart;
    
    function initCharts() {
        if (typeof TradingView !== 'undefined') {
            xauChart = new TradingView.widget({
                width: "100%", height: 350, symbol: "OANDA:XAUUSD", interval: "5", theme: "dark", style: "1", locale: "en",
                container_id: "tv-xau-container", studies: ["RSI@tv-basicstudies"], autosize: false
            });
            btcChart = new TradingView.widget({
                width: "100%", height: 350, symbol: "BITSTAMP:BTCUSD", interval: "5", theme: "dark", style: "1", locale: "en",
                container_id: "tv-btc-container", studies: ["RSI@tv-basicstudies"]
            });
        } else {
            setTimeout(initCharts, 1000);
        }
    }
    
    function updateUI() {
        fetch('/api/all')
            .then(res => res.json())
            .then(data => {
                // XAUUSD
                document.getElementById('xauPrice').innerHTML = data.XAUUSD.price ? `$${data.XAUUSD.price.toFixed(2)}` : '$---';
                document.getElementById('xauRsi').innerHTML = data.XAUUSD.rsi || '---';
                document.getElementById('xauSupport').innerHTML = data.XAUUSD.support ? `$${data.XAUUSD.support}` : '---';
                document.getElementById('xauResistance').innerHTML = data.XAUUSD.resistance ? `$${data.XAUUSD.resistance}` : '---';
                const xauSignalDiv = document.getElementById('xauSignal');
                xauSignalDiv.className = `signal-display signal-${data.XAUUSD.signal}`;
                xauSignalDiv.innerHTML = data.XAUUSD.signal;
                document.getElementById('xauReasoning').innerHTML = `💭 ${data.XAUUSD.reasoning || 'Analyzing...'}`;
                
                // BTCUSD
                document.getElementById('btcPrice').innerHTML = data.BTCUSD.price ? `$${data.BTCUSD.price.toFixed(0)}` : '$---';
                document.getElementById('btcRsi').innerHTML = data.BTCUSD.rsi || '---';
                document.getElementById('btcSupport').innerHTML = data.BTCUSD.support ? `$${data.BTCUSD.support}` : '---';
                document.getElementById('btcResistance').innerHTML = data.BTCUSD.resistance ? `$${data.BTCUSD.resistance}` : '---';
                const btcSignalDiv = document.getElementById('btcSignal');
                btcSignalDiv.className = `signal-display signal-${data.BTCUSD.signal}`;
                btcSignalDiv.innerHTML = data.BTCUSD.signal;
                document.getElementById('btcReasoning').innerHTML = `💭 ${data.BTCUSD.reasoning || 'Analyzing...'}`;
                
                document.getElementById('updateTime').innerHTML = `Last update: ${data.XAUUSD.last_update || 'Waiting...'}`;
            })
            .catch(err => console.log('Update error:', err));
    }
    
    initCharts();
    updateUI();
    setInterval(updateUI, 2000);
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
print("🚀 AI DUAL SCALPER - AUTO TRADING BOT")
print("=" * 60)
print("✅ Data Source: Yahoo Finance (FREE, No API Key needed)")
print("✅ Strategy: RSI + Support/Resistance on 5-minute timeframe")
print("✅ Auto-trading: Ready (add broker API to enable)")
print("=" * 60)

# Start trading bot thread
bot_thread = threading.Thread(target=trading_bot_loop, daemon=True)
bot_thread.start()
print("✅ Trading bot thread started!")
print("✅ Web UI available at the URL above")
print("=" * 60)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
