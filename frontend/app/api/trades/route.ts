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

function parseCsvLine(text: string): string[] {
  const result: string[] = []
  let cur = ''
  let inQuotes = false

  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (c === '"') {
      if (inQuotes && text[i + 1] === '"') {
        cur += '"'
        i++
      } else {
        inQuotes = !inQuotes
      }
    } else if (c === ',' && !inQuotes) {
      result.push(cur.trim())
      cur = ''
    } else {
      cur += c
    }
  }
  result.push(cur.trim())
  return result
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url)
    const limit = parseInt(searchParams.get('limit') || '50')
    const page = parseInt(searchParams.get('page') || '1')
    const symbol = searchParams.get('symbol')?.toUpperCase() || ''
    const regime = searchParams.get('regime')?.toUpperCase() || ''
    const search = searchParams.get('search')?.toLowerCase() || ''

    const csvPath = getFilePath(path.join('data', 'backtest_trades_log.csv'))
    if (!fs.existsSync(csvPath)) {
      return NextResponse.json({ success: false, error: 'CSV file not found' }, { status: 404 })
    }

    const content = fs.readFileSync(csvPath, 'utf-8')
    const lines = content.split('\n').filter(l => l.trim().length > 0)
    if (lines.length < 2) {
      return NextResponse.json({ success: true, trades: [], total: 0 })
    }

    const header = parseCsvLine(lines[0])
    const allTrades: any[] = []
    let totalWins = 0
    let totalLosses = 0
    let grossProfit = 0
    let grossLoss = 0

    for (let i = 1; i < lines.length; i++) {
      const row = parseCsvLine(lines[i])
      if (row.length < 11) continue

      const pnlUsd = parseFloat(row[9]) || 0
      const pnlPct = parseFloat(row[10]) || 0

      if (pnlUsd > 0) {
        totalWins++
        grossProfit += pnlUsd
      } else if (pnlUsd < 0) {
        totalLosses++
        grossLoss += Math.abs(pnlUsd)
      }

      const trade = {
        id: row[0],
        symbol: row[1],
        side: row[2],
        entryTime: row[3],
        exitTime: row[4],
        entryPrice: parseFloat(row[5]) || 0,
        exitPrice: parseFloat(row[6]) || 0,
        size: parseFloat(row[7]) || 0,
        positionValue: parseFloat(row[8]) || 0,
        pnlUsd,
        pnlPct,
        cumulativeWallet: parseFloat(row[11]) || 0,
        exitTrigger: row[12] || '',
        entryRemarks: row[13] || '',
        exitRemarks: row[14] || '',
        macroNews: row[15] || '',
        btcDrift: parseFloat(row[16]) || 0,
        regime: row[17] || 'BULL'
      }

      // Filter checks
      if (symbol && !trade.symbol.includes(symbol)) continue
      if (regime && trade.regime !== regime) continue
      if (search) {
        const hay = `${trade.symbol} ${trade.entryRemarks} ${trade.exitRemarks} ${trade.macroNews} ${trade.exitTrigger}`.toLowerCase()
        if (!hay.includes(search)) continue
      }

      allTrades.push(trade)
    }

    // Pagination (reverse to see latest first)
    const reversed = [...allTrades].reverse()
    const startIndex = (page - 1) * limit
    const paginated = reversed.slice(startIndex, startIndex + limit)

    const profitFactor = grossLoss > 0 ? (grossProfit / grossLoss).toFixed(2) : 'N/A'
    const winRate = (totalWins + totalLosses) > 0 
      ? ((totalWins / (totalWins + totalLosses)) * 100).toFixed(1) 
      : '0.0'

    return NextResponse.json({
      success: true,
      stats: {
        totalTrades: lines.length - 1,
        filteredTrades: allTrades.length,
        winRate: `${winRate}%`,
        totalWins,
        totalLosses,
        profitFactor,
        grossProfit: +grossProfit.toFixed(2),
        grossLoss: +grossLoss.toFixed(2)
      },
      page,
      limit,
      totalPages: Math.ceil(allTrades.length / limit),
      trades: paginated
    })
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 })
  }
}
