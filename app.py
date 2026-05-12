
import requests
import time
import json
import os
import threading
from datetime import datetime
from flask import Flask, render_template_string, jsonify

app = Flask(__name__)

# ============================================================
# CONFIGURATION - GET API KEYS FROM RENDER ENVIRONMENT
# ============================================================
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
TWELVE_API_KEY = os.environ.get('TWELVE_API_KEY', 'demo')
FXCM_TOKEN = os.environ.get('FXCM_TOKEN', '')  # Add your FXCM token

# Global data storage for both assets
assets_data = {
    'XAUUSD': {
        'price': None,
        'rsi': None,
        'support': None,
        'resistance': None,
        'signal': 'WAITING',
        'confidence': 'Low',
        'entry': None,
        'take_profit': None,
        'stop_loss': None,
        'trailing_stop': None,
        'reasoning': 'Awaiting first analysis...',
        'position': None,  # 'long', 'short', or None
        'position_entry_price': None,
        'position_entry_time': None,
        'highest_price': None,  # For trailing stop on long
        'lowest_price': None,   # For trailing stop on short
        'last_update': 'Never'
    },
    'BTCUSD': {
        'price': None,
        'rsi': None,
        'support': None,
        'resistance': None,
        'signal': 'WAITING',
        'confidence': 'Low',
        'entry': None,
        'take_profit': None,
        'stop_loss': None,
        'trailing_stop': None,
        'reasoning': 'Awaiting first analysis...',
        'position': None,
        'position_entry_price': None,
        'position_entry_time': None,
        'highest_price': None,
        'lowest_price': None,
        'last_update': 'Never'
    }
}

# ============================================================
# TECHNICAL ANALYSIS FUNCTIONS
# ============================================================
def calculate_rsi(prices, period=14):
    """Calculate RSI from price list"""
    if len(prices) < period + 1:
        return 50
    gains = 0
    losses = 0
    for i in range(len(prices) - period - 1, len(prices) - 1):
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
    """Calculate dynamic support and resistance using recent highs/lows"""
    if len(prices) < 20:
        return None, None
    recent = prices[-30:]
    high = max(recent)
    low = min(recent)
    range_val = high - low
    support = low + (range_val * 0.236)
    resistance = high - (range_val * 0.236)
    return round(support, 2), round(resistance, 2)

def is_near_support(price, support, asset):
    """Check if price is near support level"""
    if not support or not price:
        return False
    threshold = 1.8 if asset == 'XAUUSD' else 250
    return abs(price - support) < threshold

def is_near_resistance(price, resistance, asset):
    """Check if price is near resistance level"""
    if not resistance or not price:
        return False
    threshold = 1.8 if asset == 'XAUUSD' else 250
    return abs(price - resistance) < threshold

# ============================================================
# MARKET DATA FUNCTIONS (Twelve Data)
# ============================================================
def get_market_data(symbol, asset_key):
    """Fetch real market data from Twelve Data"""
    try:
        # Map symbol for Twelve Data API
        api_symbol = 'XAU/USD' if symbol == 'XAUUSD' else 'BTC/USD'
        url = f"https://api.twelvedata.com/time_series?symbol={api_symbol}&interval=5min&outputsize=50&apikey={TWELVE_API_KEY}"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if 'values' not in data or not data['values']:
            print(f"No values for {symbol}")
            return None
        
        prices = [float(v['close']) for v in data['values']]
        current_price = prices[-1]
        rsi = calculate_rsi(prices)
        support, resistance = calculate_support_resistance(prices)
        
        return {
            'price': current_price,
            'rsi': rsi,
            'support': support,
            'resistance': resistance,
            'history': prices
        }
    except Exception as e:
        print(f"Market data error for {symbol}: {e}")
        return None

# ============================================================
# AI SIGNAL FUNCTION (Groq)
# ============================================================
def get_ai_signal(asset_key, market_data):
    """Get trading signal from Groq AI"""
    if not GROQ_API_KEY:
        return {
            'signal': 'HOLD',
            'confidence': 'Low',
            'entry': market_data['price'],
            'takeProfit': market_data['price'] + (2 if asset_key == 'XAUUSD' else 300),
            'stopLoss': market_data['price'] - (2 if asset_key == 'XAUUSD' else 300),
            'reasoning': 'Groq API key not configured. Add GROQ_API_KEY in Render environment variables.'
        }
    
    price = market_data['price']
    rsi = market_data['rsi']
    support = market_data['support']
    resistance = market_data['resistance']
    
    near_support = is_near_support(price, support, asset_key)
    near_resistance = is_near_resistance(price, resistance, asset_key)
    
    # Check current position for profit protection advice
    position = assets_data[asset_key].get('position')
    position_entry = assets_data[asset_key].get('position_entry_price')
    
    profit_status = ""
    if position == 'long' and position_entry:
        profit_pct = ((price - position_entry) / position_entry) * 100
        profit_status = f"Currently in LONG position entered at ${position_entry:.2f}. Current profit: {profit_pct:.2f}%. "
        if profit_pct > 0.5:
            profit_status += "Consider trailing stop to protect profits."
    elif position == 'short' and position_entry:
        profit_pct = ((position_entry - price) / position_entry) * 100
        profit_status = f"Currently in SHORT position entered at ${position_entry:.2f}. Current profit: {profit_pct:.2f}%. "
        if profit_pct > 0.5:
            profit_status += "Consider trailing stop to protect profits."
    
    prompt = f"""You are a professional scalper for {asset_key}. Analyze this REAL 5-minute market data:

Price: ${price:.2f}
RSI (14): {rsi} ({'Overbought (>70)' if rsi > 70 else 'Oversold (<30)' if rsi < 30 else 'Neutral'})
Dynamic Support: ${support if support else 'N/A'}
Dynamic Resistance: ${resistance if resistance else 'N/A'}
Price Action: {'NEAR SUPPORT (BUY ZONE)' if near_support else 'NEAR RESISTANCE (SELL ZONE)' if near_resistance else 'Between levels'}
{profit_status}

Scalping Strategy Rules (5-minute timeframe):
- BUY when: Price near Support AND RSI < 35 (oversold)
- SELL when: Price near Resistance AND RSI > 65 (overbought)
- HOLD when: No clear setup OR RSI is neutral (40-60)
- If in a profitable position, recommend trailing stop to lock profits

Return ONLY valid JSON with this exact format:
{{"signal": "BUY/SELL/HOLD/CLOSE", "confidence": "High/Medium/Low", "entry": number, "takeProfit": number, "stopLoss": number, "trailingStopPct": number, "reasoning": "short reason"}}

For trailingStopPct: set 0.5 for XAUUSD (0.5% trail) or 1.0 for BTCUSD (1% trail) if in profit, otherwise 0."""

    try:
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 350
        }
        
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=15
        )
        
        result = response.json()
        content = result['choices'][0]['message']['content']
        content = content.replace('```json', '').replace('```', '').strip()
        
        return json.loads(content)
    except Exception as e:
        print(f"Groq error for {asset_key}: {e}")
        return {
            'signal': 'HOLD',
            'confidence': 'Low',
            'entry': market_data['price'],
            'takeProfit': market_data['price'] + (2 if asset_key == 'XAUUSD' else 300),
            'stopLoss': market_data['price'] - (2 if asset_key == 'XAUUSD' else 300),
            'trailingStopPct': 0,
            'reasoning': f'AI analysis temporary issue: {str(e)[:50]}'
        }

# ============================================================
# PROFIT PROTECTION (TRAILING STOP)
# ============================================================
def update_trailing_stop(asset_key, current_price, asset_data):
    """Update trailing stop to protect profits"""
    position = asset_data['position']
    entry_price = asset_data['position_entry_price']
    highest = asset_data.get('highest_price', entry_price)
    lowest = asset_data.get('lowest_price', entry_price)
    trailing_pct = asset_data.get('trailing_stop', 0)
    
    if not position or not entry_price:
        return None
    
    if position == 'long':
        # Update highest price seen
        if current_price > highest:
            highest = current_price
            asset_data['highest_price'] = highest
            
            # Calculate new trailing stop
            if trailing_pct > 0:
                new_trailing_stop = highest * (1 - trailing_pct / 100)
                # Only move stop UP (never down)
                if new_trailing_stop > asset_data['stop_loss']:
                    asset_data['stop_loss'] = new_trailing_stop
                    print(f"📈 {asset_key} Trailing stop moved up to ${new_trailing_stop:.2f}")
        
        # Check if trailing stop hit
        if current_price <= asset_data['stop_loss']:
            return 'CLOSE'
            
    elif position == 'short':
        # Update lowest price seen
        if current_price < lowest:
            lowest = current_price
            asset_data['lowest_price'] = lowest
            
            # Calculate new trailing stop
            if trailing_pct > 0:
                new_trailing_stop = lowest * (1 + trailing_pct / 100)
                # Only move stop DOWN (never up for shorts)
                if new_trailing_stop < asset_data['stop_loss']:
                    asset_data['stop_loss'] = new_trailing_stop
                    print(f"📉 {asset_key} Trailing stop moved down to ${new_trailing_stop:.2f}")
        
        # Check if trailing stop hit
        if current_price >= asset_data['stop_loss']:
            return 'CLOSE'
    
    return None

# ============================================================
# TRADING EXECUTION
# ============================================================
def execute_trade(asset_key, signal, data, market_price):
    """Execute or manage trades with profit protection"""
    asset = assets_data[asset_key]
    
    if signal == 'BUY' and asset['position'] is None:
        # Open new LONG position
        asset['position'] = 'long'
        asset['position_entry_price'] = market_price
        asset['position_entry_time'] = datetime.now().isoformat()
        asset['highest_price'] = market_price
        asset['stop_loss'] = data['stopLoss']
        asset['take_profit'] = data['takeProfit']
        asset['trailing_stop'] = data.get('trailingStopPct', 0)
        
        print(f"🟢 OPEN LONG {asset_key} @ ${market_price:.2f}")
        print(f"   TP: ${asset['take_profit']:.2f} | SL: ${asset['stop_loss']:.2f}")
        print(f"   Trail: {asset['trailing_stop']}%")
        
        # === ADD YOUR FXCM ORDER CODE HERE ===
        # if FXCM_TOKEN:
        #     send_order(asset_key, 'buy', market_price)
        
    elif signal == 'SELL' and asset['position'] is None:
        # Open new SHORT position
        asset['position'] = 'short'
        asset['position_entry_price'] = market_price
        asset['position_entry_time'] = datetime.now().isoformat()
        asset['lowest_price'] = market_price
        asset['stop_loss'] = data['stopLoss']
        asset['take_profit'] = data['takeProfit']
        asset['trailing_stop'] = data.get('trailingStopPct', 0)
        
        print(f"🔴 OPEN SHORT {asset_key} @ ${market_price:.2f}")
        print(f"   TP: ${asset['take_profit']:.2f} | SL: ${asset['stop_loss']:.2f}")
        print(f"   Trail: {asset['trailing_stop']}%")
        
        # === ADD YOUR FXCM ORDER CODE HERE ===
        
    elif signal == 'CLOSE' and asset['position'] is not None:
        # Close position (profit target hit or trailing stop triggered)
        profit = 0
        if asset['position'] == 'long':
            profit = market_price - asset['position_entry_price']
            print(f"🔒 CLOSE LONG {asset_key} @ ${market_price:.2f} | Profit: ${profit:.2f}")
        else:
            profit = asset['position_entry_price'] - market_price
            print(f"🔒 CLOSE SHORT {asset_key} @ ${market_price:.2f} | Profit: ${profit:.2f}")
        
        # Reset position
        asset['position'] = None
        asset['position_entry_price'] = None
        asset['highest_price'] = None
        asset['lowest_price'] = None
        
        # === ADD YOUR FXCM CLOSE ORDER CODE HERE ===

# ============================================================
# CHECK PROFIT TARGETS
# ============================================================
def check_profit_targets(asset_key, current_price, asset_data):
    """Check if take profit or stop loss hit"""
    if asset_data['position'] == 'long':
        if current_price >= asset_data['take_profit']:
            return 'CLOSE'  # Take profit hit
        elif current_price <= asset_data['stop_loss']:
            return 'CLOSE'  # Stop loss hit
    elif asset_data['position'] == 'short':
        if current_price <= asset_data['take_profit']:
            return 'CLOSE'  # Take profit hit
        elif current_price >= asset_data['stop_loss']:
            return 'CLOSE'  # Stop loss hit
    return None

# ============================================================
# MAIN TRADING LOOP
# ============================================================
def trading_bot_loop():
    """Main trading loop running in background for both assets"""
    print("🤖 Dual-Asset Trading Bot Started!")
    print(f"📊 Trading: XAUUSD + BTCUSD")
    print(f"⏱️  Timeframe: 5-minute candles")
    print("=" * 50)
    
    while True:
        for asset_key in ['XAUUSD', 'BTCUSD']:
            try:
                # Fetch market data
                market_data = get_market_data(asset_key, asset_key)
                
                if market_data and market_data['price']:
                    current_price = market_data['price']
                    
                    # Check if current position hit profit target
                    close_signal = check_profit_targets(asset_key, current_price, assets_data[asset_key])
                    
                    if close_signal:
                        execute_trade(asset_key, 'CLOSE', None, current_price)
                    
                    # Update trailing stop for existing positions
                    if assets_data[asset_key]['position'] is not None:
                        trail_close = update_trailing_stop(asset_key, current_price, assets_data[asset_key])
                        if trail_close == 'CLOSE':
                            execute_trade(asset_key, 'CLOSE', None, current_price)
                    
                    # Get AI signal for new trades
                    analysis = get_ai_signal(asset_key, market_data)
                    
                    # Only take new signals if no position open
                    if assets_data[asset_key]['position'] is None:
                        if analysis.get('signal') in ['BUY', 'SELL']:
                            execute_trade(asset_key, analysis['signal'], analysis, current_price)
                    
                    # Update global data for web display
                    assets_data[asset_key].update({
                        'price': current_price,
                        'rsi': market_data['rsi'],
                        'support': market_data['support'],
                        'resistance': market_data['resistance'],
                        'signal': analysis.get('signal', 'HOLD'),
                        'confidence': analysis.get('confidence', 'Medium'),
                        'entry': analysis.get('entry', current_price),
                        'take_profit': analysis.get('takeProfit', current_price + (2 if asset_key == 'XAUUSD' else 300)),
                        'stop_loss': analysis.get('stopLoss', current_price - (2 if asset_key == 'XAUUSD' else 300)),
                        'trailing_stop': analysis.get('trailingStopPct', 0),
                        'reasoning': analysis.get('reasoning', 'Analysis complete'),
                        'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
                    print(f"[{assets_data[asset_key]['last_update']}] {asset_key}: ${current_price:.2f} | RSI: {market_data['rsi']} | Signal: {analysis.get('signal')} | Pos: {assets_data[asset_key]['position']}")
                    
                else:
                    print(f"⚠️ No market data for {asset_key}")
                
                # Small delay between assets to avoid rate limiting
                time.sleep(2)
                
            except Exception as e:
                print(f"Error in {asset_key} loop: {e}")
        
        # Wait 60 seconds before next full cycle (5-minute trading frequency)
        time.sleep(60)

# ============================================================
# FLASK WEB DASHBOARD WITH TRADINGVIEW CHARTS
# ============================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🤖 AI Dual Scalper | XAUUSD + BTCUSD | Automated Trading</title>
    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
            background: linear-gradient(135deg, #0a0f1a 0%, #0f172a 100%);
            color: #eef2ff;
            padding: 20px;
            min-height: 100vh;
        }
        .container {
            max-width: 1800px;
            margin: 0 auto;
        }
        .header {
            background: rgba(17, 24, 39, 0.8);
            backdrop-filter: blur(10px);
            border-radius: 28px;
            padding: 20px 28px;
            margin-bottom: 24px;
            border: 1px solid #1e293b;
        }
        .header h1 {
            font-size: 1.8rem;
            background: linear-gradient(135deg, #fbbf24, #f59e0b);
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
        }
        .header p {
            color: #94a3b8;
            font-size: 0.85rem;
        }
        .dual-asset-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 24px;
            margin-bottom: 24px;
        }
        .asset-panel {
            background: rgba(17, 24, 39, 0.8);
            backdrop-filter: blur(10px);
            border-radius: 24px;
            border: 1px solid #1e293b;
            overflow: hidden;
        }
        .asset-header {
            background: #111827;
            padding: 16px 20px;
            font-weight: 700;
            font-size: 1.2rem;
            border-bottom: 1px solid #1e293b;
        }
        .asset-header .symbol {
            color: #fbbf24;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
            padding: 16px;
        }
        .stat-card {
            background: #0f172a;
            border-radius: 16px;
            padding: 12px;
            text-align: center;
        }
        .stat-label {
            font-size: 0.65rem;
            text-transform: uppercase;
            color: #9ca3af;
        }
        .stat-value {
            font-size: 1.3rem;
            font-weight: 700;
            font-family: monospace;
        }
        .chart-container {
            width: 100%;
            height: 350px;
            padding: 12px;
        }
        .signal-box {
            padding: 16px;
            margin: 12px;
            border-radius: 20px;
        }
        .signal-BUY {
            background: linear-gradient(135deg, rgba(16, 185, 129, 0.15), rgba(16, 185, 129, 0.05));
            border: 1px solid #10b981;
        }
        .signal-SELL {
            background: linear-gradient(135deg, rgba(239, 68, 68, 0.15), rgba(239, 68, 68, 0.05));
            border: 1px solid #ef4444;
        }
        .signal-HOLD {
            background: linear-gradient(135deg, rgba(245, 158, 11, 0.15), rgba(245, 158, 11, 0.05));
            border: 1px solid #f59e0b;
        }
        .signal-text {
            font-size: 1.8rem;
            font-weight: 800;
        }
        .signal-BUY .signal-text { color: #10b981; }
        .signal-SELL .signal-text { color: #ef4444; }
        .signal-HOLD .signal-text { color: #f59e0b; }
        .position-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.7rem;
            font-weight: 600;
        }
        .position-long {
            background: rgba(16, 185, 129, 0.2);
            color: #10b981;
            border: 1px solid #10b981;
        }
        .position-short {
            background: rgba(239, 68, 68, 0.2);
            color: #ef4444;
            border: 1px solid #ef4444;
        }
        .reasoning {
            font-size: 0.8rem;
            color: #cbd5e1;
            margin-top: 12px;
            padding-top: 12px;
            border-top: 1px solid #1e293b;
        }
        .last-update {
            font-size: 0.7rem;
            color: #64748b;
            text-align: center;
            margin-top: 16px;
        }
        @media (max-width: 1100px) {
            .dual-asset-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>⚡ AI Dual Scalper | XAUUSD + BTCUSD</h1>
        <p>Real Market Data (5-min) • Groq AI Analysis • Trailing Stop Profit Protection • TradingView Charts</p>
    </div>

    <div class="dual-asset-grid">
        <!-- XAUUSD Panel -->
        <div class="asset-panel">
            <div class="asset-header">🥇 <span class="symbol">XAUUSD (Gold)</span> - 5-Min Scalping</div>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">Price</div>
                    <div class="stat-value" id="xauPrice">$---</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Support</div>
                    <div class="stat-value" id="xauSupport">---</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Resistance</div>
                    <div class="stat-value" id="xauResistance">---</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">RSI (14)</div>
                    <div class="stat-value" id="xauRsi">---</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Position</div>
                    <div class="stat-value" id="xauPosition">---</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Trail Stop</div>
                    <div class="stat-value" id="xauTrail">---</div>
                </div>
            </div>
            <div class="chart-container" id="xauChart"></div>
            <div id="xauSignalBox" class="signal-box signal-HOLD">
                <div class="signal-text">---</div>
                <div class="reasoning">Awaiting AI analysis...</div>
            </div>
        </div>

        <!-- BTCUSD Panel -->
        <div class="asset-panel">
            <div class="asset-header">₿ <span class="symbol">BTCUSD (Bitcoin)</span> - 5-Min Scalping</div>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">Price</div>
                    <div class="stat-value" id="btcPrice">$---</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Support</div>
                    <div class="stat-value" id="btcSupport">---</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Resistance</div>
                    <div class="stat-value" id="btcResistance">---</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">RSI (14)</div>
                    <div class="stat-value" id="btcRsi">---</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Position</div>
                    <div class="stat-value" id="btcPosition">---</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Trail Stop</div>
                    <div class="stat-value" id="btcTrail">---</div>
                </div>
            </div>
            <div class="chart-container" id="btcChart"></div>
            <div id="btcSignalBox" class="signal-box signal-HOLD">
                <div class="signal-text">---</div>
                <div class="reasoning">Awaiting AI analysis...</div>
            </div>
        </div>
    </div>

    <div class="last-update" id="lastUpdate">Last update: --</div>
</div>

<script>
    let xauChart, btcChart;
    
    // Initialize TradingView charts
    function initCharts() {
        if (typeof TradingView !== 'undefined') {
            xauChart = new TradingView.widget({
                width: "100%",
                height: 350,
                symbol: "OANDA:XAUUSD",
                interval: "5",
                theme: "dark",
                style: "1",
                locale: "en",
                container_id: "xauChart",
                studies: ["RSI@tv-basicstudies"],
                hide_side_toolbar: false,
                allow_symbol_change: false
            });
            
            btcChart = new TradingView.widget({
                width: "100%",
                height: 350,
                symbol: "BITSTAMP:BTCUSD",
                interval: "5",
                theme: "dark",
                style: "1",
                locale: "en",
                container_id: "btcChart",
                studies: ["RSI@tv-basicstudies"],
                hide_side_toolbar: false,
                allow_symbol_change: false
            });
            
            console.log("TradingView charts loaded");
        } else {
            console.log("Waiting for TradingView...");
            setTimeout(initCharts, 1000);
        }
    }
    
    // Fetch and update dashboard data
    async function updateDashboard() {
        try {
            const response = await fetch('/api/all');
            const data = await response.json();
            
            // Update XAUUSD
            document.getElementById('xauPrice').innerHTML = `$${data.XAUUSD.price || '---'}`;
            document.getElementById('xauSupport').innerHTML = data.XAUUSD.support ? `$${data.XAUUSD.support}` : '---';
            document.getElementById('xauResistance').innerHTML = data.XAUUSD.resistance ? `$${data.XAUUSD.resistance}` : '---';
            
            const xauRsi = document.getElementById('xauRsi');
            xauRsi.innerHTML = data.XAUUSD.rsi || '---';
            xauRsi.style.color = (data.XAUUSD.rsi > 70) ? '#ef4444' : (data.XAUUSD.rsi < 30) ? '#10b981' : '#fbbf24';
            
            const xauPosition = document.getElementById('xauPosition');
            if (data.XAUUSD.position === 'long') {
                xauPosition.innerHTML = '🟢 LONG';
                xauPosition.className = 'stat-value position-long';
            } else if (data.XAUUSD.position === 'short') {
                xauPosition.innerHTML = '🔴 SHORT';
                xauPosition.className = 'stat-value position-short';
            } else {
                xauPosition.innerHTML = '⚪ NONE';
                xauPosition.className = 'stat-value';
            }
            
            document.getElementById('xauTrail').innerHTML = data.XAUUSD.trailing_stop ? `${data.XAUUSD.trailing_stop}%` : '---';
            
            // Update XAUUSD signal box
            const xauBox = document.getElementById('xauSignalBox');
            xauBox.className = `signal-box signal-${data.XAUUSD.signal}`;
            xauBox.innerHTML = `
                <div class="signal-text">${data.XAUUSD.signal}</div>
                <div class="reasoning">
                    💭 ${data.XAUUSD.reasoning}<br>
                    🎯 TP: $${data.XAUUSD.take_profit?.toFixed(2) || '---'} | 🛑 SL: $${data.XAUUSD.stop_loss?.toFixed(2) || '---'}
                </div>
            `;
            
            // Update BTCUSD
            document.getElementById('btcPrice').innerHTML = `$${data.BTCUSD.price?.toFixed(0) || '---'}`;
            document.getElementById('btcSupport').innerHTML = data.BTCUSD.support ? `$${data.BTCUSD.support.toFixed(0)}` : '---';
            document.getElementById('btcResistance').innerHTML = data.BTCUSD.resistance ? `$${data.BTCUSD.resistance.toFixed(0)}` : '---';
            
            const btcRsi = document.getElementById('btcRsi');
            btcRsi.innerHTML = data.BTCUSD.rsi || '---';
            btcRsi.style.color = (data.BTCUSD.rsi > 70) ? '#ef4444' : (data.BTCUSD.rsi < 30) ? '#10b981' : '#fbbf24';
            
            const btcPosition = document.getElementById('btcPosition');
            if (data.BTCUSD.position === 'long') {
                btcPosition.innerHTML = '🟢 LONG';
                btcPosition.className = 'stat-value position-long';
            } else if (data.BTCUSD.position === 'short') {
                btcPosition.innerHTML = '🔴 SHORT';
                btcPosition.className = 'stat-value position-short';
            } else {
                btcPosition.innerHTML = '⚪ NONE';
                btcPosition.className = 'stat-value';
            }
            
            document.getElementById('btcTrail').innerHTML = data.BTCUSD.trailing_stop ? `${data.BTCUSD.trailing_stop}%` : '---';
            
            // Update BTCUSD signal box
            const btcBox = document.getElementById('btcSignalBox');
            btcBox.className = `signal-box signal-${data.BTCUSD.signal}`;
            btcBox.innerHTML = `
                <div class="signal-text">${data.BTCUSD.signal}</div>
                <div class="reasoning">
                    💭 ${data.BTCUSD.reasoning}<br>
                    🎯 TP: $${data.BTCUSD.take_profit?.toFixed(0) || '---'} | 🛑 SL: $${data.BTCUSD.stop_loss?.toFixed(0) || '---'}
                </div>
            `;
            
            document.getElementById('lastUpdate').innerHTML = `Last update: ${data.XAUUSD.last_update || new Date().toLocaleTimeString()}`;
            
        } catch (error) {
            console.log("Update error:", error);
        }
    }
    
    // Initialize everything
    setTimeout(initCharts, 500);
    updateDashboard();
    setInterval(updateDashboard, 5000); // Update every 5 seconds
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
# MAIN ENTRY POINT
# ============================================================
if __name__ == '__main__':
    print("=" * 60)
    print("🤖 AI DUAL SCALPER - XAUUSD + BTCUSD")
    print("=" * 60)
    print("✅ Features:")
    print("   • Real-time market data (Twelve Data)")
    print("   • 5-minute timeframe analysis")
    print("   • Support/Resistance + RSI strategy")
    print("   • Groq AI decision making")
    print("   • Trailing stop profit protection")
    print("   • TradingView charts")
    print("=" * 60)
    
    # Start trading bot in background thread
    bot_thread = threading.Thread(target=trading_bot_loop, daemon=True)
    bot_thread.start()
    
    # Start web server
    port = int(os.environ.get('PORT', 5000))
    print(f"\n🌐 Web Dashboard: https://localhost:{port}")
    print("🚀 Bot is running in background!\n")
    
    app.run(host='0.0.0.0', port=port)
