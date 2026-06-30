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
        
        # Start point 1 day before the first trade if possible
        if not df.empty:
            start_time = pd.to_datetime(df.iloc[0]['timestamp']).timestamp()
            equity_curve.append({"time": start_time - 86400, "value": equity})
            
            for _, row in closed_trades.iterrows():
                # Rough simulation: $50 win for TP, $25 loss for SL if we don't have PNL data logged
                # In a real app, PNL should be logged to the CSV.
                if row['action'] == 'TAKE_PROFIT':
                    equity += 50.0
                else:
                    equity -= 25.0
                
                t = pd.to_datetime(row['timestamp']).timestamp()
                equity_curve.append({"time": t, "value": equity})
        
        # Add current equity
        port_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'portfolio.json')
        if os.path.exists(port_file):
            import json
            with open(port_file, 'r') as f:
                port = json.load(f)
                equity_curve.append({"time": time.time(), "value": port.get('total_value', equity)})
        
        return jsonify(equity_curve)
    except Exception as e:
        return jsonify({"error": str(e)})
