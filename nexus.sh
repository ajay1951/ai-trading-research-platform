#!/usr/bin/env bash
# ==============================================================================
# NEXUS QUANT CLI - UNIFIED CONTROL CENTER
# ==============================================================================
# One-command management for autonomous bot, frontend workstation, and telemetry.
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_FILE="$DIR/data/live_state.json"
LOG_FILE="$DIR/logs/live_trading.log"

case "$1" in
  status)
    echo "=================================================================="
    echo "           NEXUS QUANT // SYSTEM TELEMETRY & HEALTH"
    echo "=================================================================="
    if command -v pm2 >/dev/null 2>&1; then
      pm2 list
    fi
    echo ""
    echo "--- LIVE TRADING ENGINE STATE ---"
    if [ -f "$STATE_FILE" ]; then
      if command -v jq >/dev/null 2>&1; then
        CASH=$(jq -r '.cash // 0' "$STATE_FILE")
        POS_COUNT=$(jq -r '(.positions // {}) | keys | length' "$STATE_FILE")
        CYCLE=$(jq -r '.cycle_count // 1' "$STATE_FILE")
        MILESTONE=$(jq -r '.target_milestone // 150' "$STATE_FILE")
        echo "  Wallet Cash:      \$$CASH"
        echo "  Active Positions: $POS_COUNT"
        echo "  Cycle Count:      $CYCLE (Target Milestone: \$$MILESTONE)"
        echo ""
        echo "  Open Position Details:"
        jq -r '(.positions // {}) | to_entries[] | "    [\(.key)] Size: \(.value.size) | Entry: $\(.value.entry_price) | Short: \(.value.is_short)"' "$STATE_FILE"
      else
        cat "$STATE_FILE"
      fi
    else
      echo "  [i] State file not yet created. Engine will generate it on first hourly bar."
    fi
    echo "=================================================================="
    ;;

  logs)
    echo "Streaming live trading logs (Ctrl+C to exit)..."
    if [ -f "$LOG_FILE" ]; then
      tail -f -n 50 "$LOG_FILE"
    else
      pm2 logs nexus-bot
    fi
    ;;

  logs-ui)
    echo "Streaming frontend workstation logs (Ctrl+C to exit)..."
    pm2 logs nexus-frontend
    ;;

  restart)
    echo "Restarting Nexus services..."
    pm2 restart nexus-bot nexus-frontend
    echo "[✓] Services restarted successfully."
    ;;

  stop)
    echo "Stopping Nexus services..."
    pm2 stop nexus-bot nexus-frontend
    echo "[✓] Services stopped."
    ;;

  start)
    echo "Starting Nexus services..."
    pm2 start nexus-bot nexus-frontend
    echo "[✓] Services started."
    ;;

  update)
    echo "Updating Nexus from GitHub..."
    cd "$DIR"
    git pull origin main
    echo "Rebuilding frontend workstation..."
    cd "$DIR/frontend"
    npm install
    npm run build
    cd "$DIR"
    pm2 restart nexus-bot nexus-frontend
    echo "[✓] Nexus is updated and running the latest code!"
    ;;

  *)
    echo "NEXUS QUANT COMMAND CENTER"
    echo "Usage: ./nexus.sh [command]"
    echo ""
    echo "Commands:"
    echo "  status    -> Display live wallet balance, open trades, and PM2 health"
    echo "  logs      -> Stream real-time autonomous trading execution logs"
    echo "  logs-ui   -> Stream Next.js web workstation server logs"
    echo "  restart   -> Cleanly reboot bot and web interface"
    echo "  update    -> Pull latest code from GitHub, rebuild frontend, and restart"
    echo "  stop      -> Gracefully suspend trading and workstation"
    echo "  start     -> Resume trading and workstation"
    echo ""
    ;;
esac
