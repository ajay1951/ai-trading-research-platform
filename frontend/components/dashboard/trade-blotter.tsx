'use client'

import React, { useEffect, useState } from 'react'
import { Search, ArrowUpRight, ArrowDownRight, ChevronLeft, ChevronRight, Filter } from 'lucide-react'

interface Trade {
  id: string
  symbol: string
  side: 'LONG' | 'SHORT'
  entryTime: string
  exitTime: string
  entryPrice: number
  exitPrice: number
  size: number
  positionValue: number
  pnlUsd: number
  pnlPct: number
  cumulativeWallet: number
  exitTrigger: string
  entryRemarks: string
  exitRemarks: string
  macroNews: string
  regime: string
}

export function TradeBlotter() {
  const [trades, setTrades] = useState<Trade[]>([])
  const [stats, setStats] = useState<any>(null)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [search, setSearch] = useState('')
  const [regime, setRegime] = useState('')
  const [symbolFilter, setSymbolFilter] = useState('')
  const [isLoading, setIsLoading] = useState(true)

  async function loadTrades() {
    try {
      setIsLoading(true)
      const params = new URLSearchParams({
        page: String(page),
        limit: '25',
        search,
        regime,
        symbol: symbolFilter
      })
      const res = await fetch(`/api/trades?${params}`)
      const json = await res.json()
      if (json.success) {
        setTrades(json.trades || [])
        setStats(json.stats || {})
        setTotalPages(json.totalPages || 1)
      }
    } catch (err) {
      console.error('Failed to load trades blotter', err)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadTrades()
  }, [page, regime, symbolFilter])

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setPage(1)
    loadTrades()
  }

  const exportCsv = () => {
    if (!trades || trades.length === 0) return
    const headers = ['id', 'symbol', 'side', 'entryTime', 'exitTime', 'entryPrice', 'exitPrice', 'size', 'pnlUsd', 'pnlPct', 'exitTrigger', 'macroNews', 'regime']
    const rows = trades.map(t => [
      t.id, t.symbol, t.side, t.entryTime, t.exitTime, t.entryPrice, t.exitPrice, t.size, t.pnlUsd, t.pnlPct, `"${t.exitTrigger}"`, `"${t.macroNews}"`, t.regime
    ])
    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map(e => e.join(','))].join('\n')
    const encodedUri = encodeURI(csvContent)
    const link = document.createElement('a')
    link.setAttribute('href', encodedUri)
    link.setAttribute('download', `blotter_trades_${new Date().toISOString().slice(0,10)}.csv`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  return (
    <div className="flex flex-col h-full bg-[#0a0d14] overflow-hidden">
      {/* Header with blotter KPIs */}
      <div className="flex h-7 shrink-0 items-center justify-between border-b border-white/[0.08] bg-[#07090e] px-3">
        <div className="flex items-center gap-2">
          <h3 className="font-mono text-[11px] font-bold text-slate-100 uppercase tracking-wider">
            TRADE BLOTTER
          </h3>
          <span className="text-slate-600">|</span>
          <span className="font-mono text-[10px] text-slate-400">2,331 Fills Audit Ledger</span>
        </div>

        {/* Quick KPI pills */}
        <div className="flex items-center gap-3 font-mono text-[11px]">
          <div className="text-slate-400">
            Fills: <span className="text-slate-100 font-bold tabular-nums">{stats?.totalTrades || 2331}</span>
          </div>
          <span className="text-slate-700">·</span>
          <div className="text-slate-400">
            Win Rate: <span className="text-emerald-400 font-bold tabular-nums">{stats?.winRate || '58.9%'}</span>
          </div>
          <span className="text-slate-700">·</span>
          <div className="text-slate-400">
            Profit Factor: <span className="text-slate-100 font-bold tabular-nums">{stats?.profitFactor || '1.23'}</span>
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex h-8 shrink-0 items-center justify-between gap-2 border-b border-white/[0.06] bg-[#090c13] px-3 py-1">
        <form onSubmit={handleSearchSubmit} className="flex flex-1 items-center gap-2 max-w-sm">
          <div className="relative w-full">
            <Search className="absolute left-2 top-2 size-3 text-slate-500" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search catalyst (e.g. CPI, FTX, Halving)..."
              className="w-full rounded border border-slate-800 bg-[#06080d] py-0.5 pl-6 pr-2 font-mono text-[11px] text-slate-200 placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
            />
          </div>
        </form>

        {/* Regime selector + Export CSV */}
        <div className="flex items-center gap-2 font-mono text-[11px]">
          <div className="flex items-center gap-1">
            <span className="text-slate-500 text-[10px] uppercase">Regime:</span>
            {(['', 'BULL', 'BEAR'] as const).map(r => (
              <button
                key={r}
                onClick={() => { setRegime(r); setPage(1) }}
                className={`px-1.5 py-0.5 rounded text-[10px] font-semibold transition-colors ${
                  regime === r
                    ? 'bg-slate-800 text-slate-100 border border-slate-700'
                    : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                {r === '' ? 'ALL' : r}
              </button>
            ))}
          </div>

          <button
            onClick={exportCsv}
            className="rounded border border-slate-700 bg-slate-800/80 px-2 py-0.5 text-[10px] font-bold text-slate-200 hover:bg-slate-700 transition-colors"
          >
            EXPORT CSV
          </button>
        </div>
      </div>

      {/* Trades Table */}
      <div className="overflow-x-auto flex-1">
        <table className="w-full text-left font-mono text-[11px]">
          <thead>
            <tr className="border-b border-white/[0.06] bg-slate-900/50 text-[10px] uppercase text-slate-400">
              <th className="py-1.5 pl-3 pr-2">Fill Date</th>
              <th className="px-2 py-1.5">Asset</th>
              <th className="px-2 py-1.5">Action</th>
              <th className="px-2 py-1.5 text-right">Entry</th>
              <th className="px-2 py-1.5 text-right">Exit</th>
              <th className="px-2 py-1.5 text-right">Net PnL</th>
              <th className="px-2 py-1.5">Exit Trigger</th>
              <th className="py-1.5 pl-2 pr-3">Macro Catalyst / Remarks</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.02]">
            {trades.map(t => {
              const isProfit = t.pnlUsd >= 0
              return (
                <tr key={t.id} className="hover:bg-slate-900/40 transition-colors">
                  <td className="py-1 pl-3 pr-2 text-slate-400 tabular-nums text-[10px]">
                    {t.entryTime.slice(0, 16).replace('T', ' ')}
                  </td>
                  <td className="px-2 py-1 font-bold text-slate-200 text-[11px]">
                    {t.symbol}
                  </td>
                  <td className="px-2 py-1">
                    <span
                      className={`rounded px-1 py-0.2 text-[9px] font-bold ${
                        t.side === 'LONG'
                          ? 'bg-emerald-950/60 text-emerald-300 border border-emerald-500/30'
                          : 'bg-rose-950/60 text-rose-300 border border-rose-500/30'
                      }`}
                    >
                      {t.side}
                    </span>
                  </td>
                  <td className="px-2 py-1 text-right tabular-nums text-slate-300">
                    ${t.entryPrice.toFixed(t.entryPrice < 2 ? 4 : 2)}
                  </td>
                  <td className="px-2 py-1 text-right tabular-nums text-slate-300">
                    ${t.exitPrice.toFixed(t.exitPrice < 2 ? 4 : 2)}
                  </td>
                  <td className="px-2 py-1 text-right tabular-nums">
                    <span className={`font-bold ${isProfit ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {isProfit ? '+' : ''}${t.pnlUsd.toFixed(2)} ({isProfit ? '+' : ''}{t.pnlPct.toFixed(1)}%)
                    </span>
                  </td>
                  <td className="px-2 py-1 text-slate-300 text-[10px]">
                    <span className="line-clamp-1 max-w-[180px]">{t.exitTrigger}</span>
                  </td>
                  <td className="py-1 pl-2 pr-3 text-slate-400 text-[10px]">
                    <span className="line-clamp-1 max-w-[280px]" title={t.entryRemarks || t.exitRemarks}>
                      {t.macroNews ? `[${t.macroNews}] ` : ''}{t.entryRemarks || t.exitRemarks}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      <div className="flex items-center justify-between border-t border-white/[0.06] bg-slate-950/80 px-4 py-2 font-mono text-xs">
        <span className="text-slate-400 text-[11px]">
          Showing Page <span className="text-slate-200 font-bold">{page}</span> of <span className="text-slate-200 font-bold">{totalPages}</span>
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="flex size-7 items-center justify-center rounded border border-slate-800 bg-slate-900 text-slate-300 disabled:opacity-30 hover:bg-slate-800"
          >
            <ChevronLeft className="size-4" />
          </button>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="flex size-7 items-center justify-center rounded border border-slate-800 bg-slate-900 text-slate-300 disabled:opacity-30 hover:bg-slate-800"
          >
            <ChevronRight className="size-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
