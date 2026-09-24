import { NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

function getFilePath(relPath: string): string {
  const p1 = path.resolve(/*turbopackIgnore: true*/ process.cwd(), relPath)
  if (fs.existsSync(p1)) return p1
  const p2 = path.resolve(/*turbopackIgnore: true*/ process.cwd(), '..', relPath)
  if (fs.existsSync(p2)) return p2
  return p1
}

const SYMBOLS = [
  'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT',
  'DOGE/USDT', 'ADA/USDT', 'AVAX/USDT', 'LINK/USDT', 'NEAR/USDT',
  'LTC/USDT', 'DOT/USDT', 'SUI/USDT'
]

export async function GET() {
  try {
    const screenerResults: any[] = []

    // Read BTC data first to calculate Relative Strength vs BTC
    let btcReturn7d = 0.0
    const btcPath = getFilePath(path.join('data', 'BTCUSDT_1h_historical.csv'))
    if (fs.existsSync(btcPath)) {
      const lines = fs.readFileSync(btcPath, 'utf-8').split('\n').filter(l => l.trim().length > 0)
      if (lines.length > 168) {
        const cNow = parseFloat(lines[lines.length - 1].split(',')[4])
        const c7d = parseFloat(lines[lines.length - 168].split(',')[4])
        if (c7d > 0) btcReturn7d = (cNow - c7d) / c7d
      }
    }

    for (const sym of SYMBOLS) {
      const cleanSym = sym.replace('/', '').toUpperCase()
      const csvPath = getFilePath(path.join('data', `${cleanSym}_1h_historical.csv`))
      if (!fs.existsSync(csvPath)) continue

      const lines = fs.readFileSync(csvPath, 'utf-8').split('\n').filter(l => l.trim().length > 0)
      if (lines.length < 168) continue

      const closes: number[] = []
      const highs: number[] = []
      const lows: number[] = []
      const volumes: number[] = []

      const recent = lines.slice(-480) // 20 days of 1h bars
      for (const line of recent) {
        const parts = line.split(',')
        if (parts.length >= 6) {
          highs.push(parseFloat(parts[2]))
          lows.push(parseFloat(parts[3]))
          closes.push(parseFloat(parts[4]))
          volumes.push(parseFloat(parts[5]))
        }
      }

      if (closes.length < 24) continue

      const cCurr = closes[closes.length - 1]
      const c7d = closes[Math.max(0, closes.length - 168)]
      const ret7d = (cCurr - c7d) / c7d
      const rsBtc = ret7d - btcReturn7d

      // Volume Expansion Factor: 24h vol / avg 20d 24h vol
      const vol24h = volumes.slice(-24).reduce((a, b) => a + b, 0)
      const avgVol24h = volumes.reduce((a, b) => a + b, 0) / (volumes.length / 24)
      const vef = avgVol24h > 0 ? (vol24h / avgVol24h) : 1.0

      // Donchian Breakout Score (20-day high/low)
      const h20 = Math.max(...highs)
      const l20 = Math.min(...lows)
      const rng = h20 - l20
      const donchian = rng > 0 ? (cCurr - l20) / rng : 0.5

      // RSI 14
      let rsi = 50.0
      if (closes.length >= 15) {
        let gains = 0, losses = 0
        for (let i = closes.length - 14; i < closes.length; i++) {
          const diff = closes[i] - closes[i - 1]
          if (diff > 0) gains += diff
          else losses += Math.abs(diff)
        }
        const rs = losses > 0 ? (gains / 14) / (losses / 14) : 100
        rsi = 100 - (100 / (1 + rs))
      }

      // Rank composite score
      const compositeScore = (rsBtc * 0.4) + (donchian * 0.4) + (Math.min(vef, 3.0) * 0.2)

      let status = 'NEUTRAL'
      let actionTag = 'HOLD'
      if (donchian >= 0.85 && rsBtc > 0.05) {
        status = 'BREAKOUT_RUNNER'
        actionTag = 'TOP_MOMENTUM_LONG'
      } else if (rsi >= 68.0 && donchian < 0.6) {
        status = 'OVERBOUGHT_EXHAUSTION'
        actionTag = 'BEAR_SHORT_CANDIDATE'
      } else if (rsBtc < -0.05) {
        status = 'UNDERPERFORMER'
        actionTag = 'AVOID'
      }

      screenerResults.push({
        symbol: sym,
        price: cCurr,
        ret7dPct: +(ret7d * 100).toFixed(2),
        rsBtcPct: +(rsBtc * 100).toFixed(2),
        vef: +vef.toFixed(2),
        donchianScore: +donchian.toFixed(2),
        rsi14: +rsi.toFixed(1),
        compositeScore: +compositeScore.toFixed(3),
        status,
        actionTag
      })
    }

    // Sort by composite score descending
    screenerResults.sort((a, b) => b.compositeScore - a.compositeScore)

    return NextResponse.json({
      success: true,
      timestamp: new Date().toISOString(),
      btcMacroBenchmark7d: +(btcReturn7d * 100).toFixed(2),
      screener: screenerResults
    })
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 })
  }
}
