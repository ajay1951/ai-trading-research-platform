from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import pandas as pd
import os
import json
import ccxt
import time

app = Flask(__name__)
CORS(app)
DATA_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'live_trades.csv')
PORTFOLIO_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'portfolio.json')
exchange = ccxt.binance({'enableRateLimit': True})

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/trades')
def get_trades():
    if not os.path.exists(DATA_FILE):
        return jsonify([])
    try:
        df = pd.read_csv(DATA_FILE)
        trades = df.tail(100).to_dict(orient='records')
        return jsonify(trades)
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/chart')
def get_chart():
    asset = request.args.get('asset', 'BTC/USDT')
    timeframe = request.args.get('timeframe', '15m')
    try:
        formatted_data = []
        last_timestamp = 0
        
        # 1. Load Massive Historical Data from InfluxDB
        symbol_clean = asset.replace("/", "")
        
        try:
            from influxdb_client import InfluxDBClient
            client = InfluxDBClient(url="http://localhost:8086", token="institutional_super_secret_token_2026", org="quant_fund", timeout=600000)
            query_api = client.query_api()
            
            # Query last 150,000 candles instantly
            query = f'''
                from(bucket: "crypto_mtf")
                |> range(start: -10y)
                |> filter(fn: (r) => r["_measurement"] == "crypto_mtf_data")
                |> filter(fn: (r) => r["asset"] == "{symbol_clean}")
                |> filter(fn: (r) => r["timeframe"] == "{timeframe}")
                |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
                |> tail(n: 150000)
            '''
            result = query_api.query_data_frame(query=query)
            client.close()
            
            df_hist = None
            if isinstance(result, list):
                if len(result) > 0:
                    df_hist = result[0]
            else:
                df_hist = result
                
            if df_hist is not None and not df_hist.empty:
                # Vectorized conversion
                df_hist['time'] = df_hist['_time'].astype('int64') // 10**9
                df_hist = df_hist[['time', 'open', 'high', 'low', 'close', 'volume']]
                
                hist_records = df_hist.to_dict(orient='records')
                formatted_data.extend(hist_records)
                
                if formatted_data:
                    last_timestamp = formatted_data[-1]["time"] * 1000 # Convert back to ms for CCXT logic
        except Exception as e:
            print(f"Error loading historical data from InfluxDB: {e}")

        # 2. Fetch Live Data to bridge the gap and stay real-time
        ohlcv = exchange.fetch_ohlcv(asset, timeframe=timeframe, limit=500)
        
        for row in ohlcv:
            # Only append live candles that are newer than our historical data
            if row[0] > last_timestamp:
                formatted_data.append({
                    "time": row[0] / 1000,
                    "open": row[1],
                    "high": row[2],
                    "low": row[3],
                    "close": row[4],
                    "volume": row[5]
                })
                
        return jsonify(formatted_data)
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/portfolio')
def get_portfolio():
    if not os.path.exists(PORTFOLIO_FILE):
        return jsonify({"cash": 10000.0, "realized_pnl": 0.0, "positions": {}, "total_value": 10000.0})
    try:
        with open(PORTFOLIO_FILE, 'r') as f:
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/ticker')
def get_ticker():
    """Proxy Binance ticker through Flask to avoid browser CORS issues."""
    try:
        tickers = exchange.fetch_tickers(['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT'])
        result = {}
        for symbol, data in tickers.items():
            result[symbol] = {
                "last": data.get('last', 0),
                "change": data.get('percentage', 0),
                "high": data.get('high', 0),
                "low": data.get('low', 0),
                "volume": data.get('baseVolume', 0)
            }
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/stats')
def get_stats():
    """Calculate win rate and trade statistics from the execution log."""
    if not os.path.exists(DATA_FILE):
        return jsonify({"total_trades": 0, "win_rate": 0, "avg_pnl": 0, "best_trade": 0, "worst_trade": 0})
    try:
        df = pd.read_csv(DATA_FILE)
        # Filter only closing actions (TAKE_PROFIT and STOP_LOSS have clear outcomes)
        tp = df[df['action'] == 'TAKE_PROFIT']
        sl = df[df['action'] == 'STOP_LOSS']
        total_closed = len(tp) + len(sl)
        
        if total_closed == 0:
            # Fallback: count all directional trades
            directional = df[df['action'].isin(['LONG', 'SHORT'])]
            return jsonify({
                "total_trades": len(directional),
                "closed_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0,
                "open_positions": len(directional) - len(tp) - len(sl)
            })
        
        wins = len(tp)
        losses = len(sl)
        win_rate = (wins / total_closed * 100) if total_closed > 0 else 0
        
        return jsonify({
            "total_trades": len(df[df['action'].isin(['LONG', 'SHORT'])]),
            "closed_trades": total_closed,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1),
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/equity')
def get_equity():
    """Calculate portfolio equity curve from trade history."""
    if not os.path.exists(DATA_FILE):
        return jsonify([{"time": time.time(), "value": 10000.0}])
    try:
        df = pd.read_csv(DATA_FILE)
        closed_trades = df[df['action'].isin(['TAKE_PROFIT', 'STOP_LOSS'])]
        
        equity = 10000.0
        equity_curve = []
        
        if not df.empty:
            start_time = pd.to_datetime(df.iloc[0]['timestamp']).timestamp()
            equity_curve.append({"time": start_time - 86400, "value": equity})
            
            for _, row in closed_trades.iterrows():
                if row['action'] == 'TAKE_PROFIT':
                    equity += 50.0
                else:
                    equity -= 25.0
                
                t = pd.to_datetime(row['timestamp']).timestamp()
                equity_curve.append({"time": t, "value": equity})
        
        port_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'portfolio.json')
        if os.path.exists(port_file):
            with open(port_file, 'r') as f:
                port = json.load(f)
                equity_curve.append({"time": time.time(), "value": port.get('total_value', equity)})
        
        return jsonify(equity_curve)
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/ping')
def ping():
    """Health check endpoint."""
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    os.makedirs(os.path.join(os.path.dirname(__file__), 'templates'), exist_ok=True)
    app.run(debug=True, port=5000)
