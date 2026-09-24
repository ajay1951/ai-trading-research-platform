import { NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

function getFilePath(relPath: string): string {
  // Check both relative to project root and relative to frontend dir
  const p1 = path.resolve(/*turbopackIgnore: true*/ process.cwd(), relPath)
  if (fs.existsSync(p1)) return p1
  const p2 = path.resolve(/*turbopackIgnore: true*/ process.cwd(), '..', relPath)
  if (fs.existsSync(p2)) return p2
  return p1
}

export async function GET() {
  try {
    const statePath = getFilePath(path.join('data', 'live_state.json'))
    let stateData = {
      cash: 50.0,
      positions: {},
      trades: [],
      cycle_count: 1,
      current_cycle_base: 50.0,
      target_milestone: 150.0,
      last_bar_ts: 0
    }

    if (fs.existsSync(statePath)) {
      const raw = fs.readFileSync(statePath, 'utf-8')
      stateData = JSON.parse(raw)
    }

    // Read recent live trading logs
    const logPath = getFilePath(path.join('logs', 'live_trading.log'))
    let recentLogs: string[] = []
    if (fs.existsSync(logPath)) {
      const logRaw = fs.readFileSync(logPath, 'utf-8')
      const lines = logRaw.split('\n').filter(l => l.trim().length > 0)
      recentLogs = lines.slice(-40)
    }

    // Calculate open equity mark-to-market estimate
    let openPositionsValue = 0
    const positionsList = Object.entries(stateData.positions || {}).map(([sym, pos]: [string, any]) => {
      const size = pos.size || 0
      const entryPrice = pos.entry_price || 0
      const notional = size * entryPrice
      openPositionsValue += notional
      return {
        symbol: sym,
        size,
        entryPrice,
        highestPrice: pos.highest_price || entryPrice,
        lowestPrice: pos.lowest_price || entryPrice,
        isShort: pos.is_short || false,
        entryTs: pos.entry_ts || '',
        notional
      }
    })

    const totalEquity = (stateData.cash || 0) + openPositionsValue
    const cycleProgressPct = Math.min(
      100,
      Math.max(0, ((totalEquity - (stateData.current_cycle_base || 50)) / ((stateData.target_milestone || 150) - (stateData.current_cycle_base || 50))) * 100)
    )

    return NextResponse.json({
      success: true,
      cash: stateData.cash || 0,
      totalEquity,
      openPositionsValue,
      positions: positionsList,
      cycleCount: stateData.cycle_count || 1,
      currentCycleBase: stateData.current_cycle_base || 50.0,
      targetMilestone: stateData.target_milestone || 150.0,
      cycleProgressPct,
      recentLogs,
      lastUpdated: new Date().toISOString()
    })
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 })
  }
}
