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

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url)
    let symbol = searchParams.get('symbol') || 'BTC/USDT'
    const cleanSym = symbol.replace('/', '').toUpperCase()

    // 1. Try Binance Public REST API
    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 2500)
      const res = await fetch(`https://api.binance.com/api/v3/klines?symbol=${cleanSym}&interval=1h&limit=120`, {
        signal: controller.signal
      })
      clearTimeout(timeout)

      if (res.ok) {
        const rawKlines = await res.json()
        if (Array.isArray(rawKlines) && rawKlines.length > 0) {
          const klines = rawKlines.map((k: any) => ({
            time: Math.floor(k[0] / 1000),
            open: parseFloat(k[1]),
            high: parseFloat(k[2]),
            low: parseFloat(k[3]),
            close: parseFloat(k[4]),
            volume: parseFloat(k[5])
          }))

          const latest = klines[klines.length - 1]
          const prev = klines[klines.length - 2] || latest
          const change24h = ((latest.close - klines[Math.max(0, klines.length - 24)].close) / klines[Math.max(0, klines.length - 24)].close) * 100

          return NextResponse.json({
            success: true,
            source: 'BINANCE_LIVE',
            symbol,
            ticker: {
              price: latest.close,
              high24h: Math.max(...klines.slice(-24).map(k => k.high)),
              low24h: Math.min(...klines.slice(-24).map(k => k.low)),
              change24h,
              volume24h: klines.slice(-24).reduce((sum, k) => sum + k.volume * k.close, 0)
            },
            klines
          })
        }
      }
    } catch {
      // Fallback to local dataset
    }

    // 2. Fallback: Parse local 1h CSV from data/
    const csvPath = getFilePath(path.join('data', `${cleanSym}_1h_historical.csv`))
    if (fs.existsSync(csvPath)) {
      const content = fs.readFileSync(csvPath, 'utf-8')
      const lines = content.split('\n').filter(l => l.trim().length > 0)
      const klines: any[] = []

      // Read last 120 lines
      const sliceLines = lines.slice(-120)
      for (const line of sliceLines) {
        const parts = line.split(',')
        if (parts.length < 6) continue
        const tStr = parts[0].trim()
        const ts = !isNaN(Number(tStr)) 
          ? (Number(tStr) > 1e11 ? Math.floor(Number(tStr) / 1000) : Number(tStr))
          : Math.floor(new Date(tStr).getTime() / 1000)
        
        const open = parseFloat(parts[1])
        const high = parseFloat(parts[2])
        const low = parseFloat(parts[3])
        const close = parseFloat(parts[4])
        const volume = parseFloat(parts[5])

        if (!isNaN(close) && !isNaN(ts)) {
          klines.push({ time: ts, open, high, low, close, volume })
        }
      }

      if (klines.length > 0) {
        const latest = klines[klines.length - 1]
        const change24h = ((latest.close - klines[Math.max(0, klines.length - 24)].close) / klines[Math.max(0, klines.length - 24)].close) * 100

        return NextResponse.json({
          success: true,
          source: 'LOCAL_HISTORICAL_CACHE',
          symbol,
          ticker: {
            price: latest.close,
            high24h: Math.max(...klines.slice(-24).map(k => k.high)),
            low24h: Math.min(...klines.slice(-24).map(k => k.low)),
            change24h,
            volume24h: klines.slice(-24).reduce((sum, k) => sum + (k.volume || 0) * k.close, 0)
          },
          klines
        })
      }
    }

    return NextResponse.json({ success: false, error: 'Data unavailable for symbol' }, { status: 404 })
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 })
  }
}
