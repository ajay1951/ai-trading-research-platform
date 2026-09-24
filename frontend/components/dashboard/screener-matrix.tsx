'use client'

import React, { useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'

interface ScreenerItem {
  symbol: string
  price: number
  ret7dPct: number
  rsBtcPct: number
  vef: number
  donchianScore: number
  rsi14: number
  compositeScore: number
  status: string
  actionTag: string
}

export function ScreenerMatrix({ onSelectSymbol }: { onSelectSymbol?: (sym: string) => void }) {
  const [data, setData] = useState<ScreenerItem[]>([])
  const [btcBenchmark, setBtcBenchmark] = useState(0)
  const [isLoading, setIsLoading] = useState(true)

  async function loadScreener() {
    try {
      setIsLoading(true)
      const res = await fetch('/api/screener')
      const json = await res.json()
      if (json.success) {
        setData(json.screener || [])
        setBtcBenchmark(json.btcMacroBenchmark7d || 0)
      }
    } catch (err) {
      console.error('Failed to load screener', err)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadScreener()
  }, [])

  return (
    <div className="flex flex-col h-full bg-[#0a0d14] overflow-hidden">
      {/* Header */}
      <div className="flex h-7 shrink-0 items-center justify-between border-b border-white/[0.08] bg-[#07090e] px-3">
        <div className="flex items-center gap-2">
          <h3 className="font-mono text-[11px] font-bold text-slate-100 uppercase tracking-wider">
            CROSS-SECTIONAL MOMENTUM SCREENER
          </h3>
          <span className="text-slate-600">|</span>
          <span className="font-mono text-[10px] text-slate-400">13 Liquid Altcoins Ranked</span>
        </div>

        <div className="flex items-center gap-3 font-mono text-[11px]">
          <span className="text-slate-400">
            BTC Benchmark: <span className={`font-semibold tabular-nums ${btcBenchmark >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{btcBenchmark >= 0 ? '+' : ''}{btcBenchmark.toFixed(2)}%</span>
          </span>
          <button
            onClick={loadScreener}
            className="flex size-5 items-center justify-center rounded text-slate-400 hover:text-slate-200"
            title="Refresh Screener"
          >
            <RefreshCw className={`size-3 ${isLoading ? 'animate-spin text-amber-400' : ''}`} />
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto flex-1">
        <table className="w-full text-left font-mono text-[11px]">
          <thead>
            <tr className="border-b border-white/[0.06] bg-slate-900/50 text-[10px] uppercase text-slate-400">
              <th className="py-1.5 pl-3 pr-2">Rank</th>
              <th className="px-2 py-1.5">Asset</th>
              <th className="px-2 py-1.5 text-right">Price</th>
              <th className="px-2 py-1.5 text-right">7d Return</th>
              <th className="px-2 py-1.5 text-right">RS vs BTC</th>
              <th className="px-2 py-1.5 text-right">Volume (VEF)</th>
              <th className="px-2 py-1.5 text-right">Donchian 20d</th>
              <th className="px-2 py-1.5 text-right">RSI 14</th>
              <th className="py-1.5 pl-2 pr-3 text-right">Engine Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.02]">
            {isLoading && data.length === 0 ? (
              Array.from({ length: 6 }).map((_, i) => (
                <tr key={i} className="animate-pulse">
                  <td className="py-2 pl-3 pr-2"><div className="h-2.5 w-4 rounded-xs bg-white/[0.05]" /></td>
                  <td className="px-2 py-2"><div className="h-2.5 w-16 rounded-xs bg-white/[0.05]" /></td>
                  <td className="px-2 py-2 text-right"><div className="h-2.5 w-14 ml-auto rounded-xs bg-white/[0.05]" /></td>
                  <td className="px-2 py-2 text-right"><div className="h-2.5 w-10 ml-auto rounded-xs bg-white/[0.05]" /></td>
                  <td className="px-2 py-2 text-right"><div className="h-2.5 w-10 ml-auto rounded-xs bg-white/[0.05]" /></td>
                  <td className="px-2 py-2 text-right"><div className="h-2.5 w-8 ml-auto rounded-xs bg-white/[0.05]" /></td>
                  <td className="px-2 py-2 text-right"><div className="h-2.5 w-8 ml-auto rounded-xs bg-white/[0.05]" /></td>
                  <td className="px-2 py-2 text-right"><div className="h-2.5 w-8 ml-auto rounded-xs bg-white/[0.05]" /></td>
                  <td className="py-2 pl-2 pr-3 text-right"><div className="h-2.5 w-16 ml-auto rounded-xs bg-white/[0.05]" /></td>
                </tr>
              ))
            ) : data.map((item, idx) => {
              const isLong = item.actionTag.includes('LONG')
              const isShort = item.actionTag.includes('SHORT')
              return (
                <tr
                  key={item.symbol}
                  onClick={() => onSelectSymbol && onSelectSymbol(item.symbol)}
                  className="cursor-pointer transition-colors hover:bg-slate-900/50"
                >
                  <td className="py-1 pl-3 pr-2 font-bold text-slate-500 text-[10px]">
                    #{idx + 1}
                  </td>
                  <td className="px-2 py-1 font-bold text-slate-200">
                    {item.symbol}
                  </td>
                  <td className="px-2 py-1 text-right tabular-nums text-slate-300">
                    ${item.price.toFixed(item.price < 2 ? 4 : 2)}
                  </td>
                  <td className={`px-2 py-1 text-right tabular-nums font-semibold ${item.ret7dPct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {item.ret7dPct >= 0 ? '+' : ''}{item.ret7dPct.toFixed(1)}%
                  </td>
                  <td className={`px-2 py-1 text-right tabular-nums font-bold ${item.rsBtcPct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {item.rsBtcPct >= 0 ? '+' : ''}{item.rsBtcPct.toFixed(1)}%
                  </td>
                  <td className="px-2 py-1 text-right tabular-nums text-slate-300">
                    {item.vef.toFixed(2)}x
                  </td>
                  <td className="px-2 py-1 text-right tabular-nums">
                    <span className={`rounded px-1 py-0.2 text-[9px] font-bold ${
                      item.donchianScore >= 0.8 ? 'bg-emerald-950/60 text-emerald-300 border border-emerald-500/30' : 'text-slate-400'
                    }`}>
                      {(item.donchianScore * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="px-2 py-1 text-right tabular-nums">
                    <span className={item.rsi14 >= 68 ? 'text-rose-400 font-bold' : item.rsi14 <= 35 ? 'text-emerald-400 font-bold' : 'text-slate-300'}>
                      {item.rsi14.toFixed(1)}
                    </span>
                  </td>
                  <td className="py-1 pl-2 pr-3 text-right">
                    <span
                      className={`inline-block rounded px-1.5 py-0.2 text-[9px] font-bold uppercase tracking-wide border ${
                        isLong
                          ? 'border-emerald-500/40 bg-emerald-950/50 text-emerald-300'
                          : isShort
                          ? 'border-rose-500/40 bg-rose-950/50 text-rose-300'
                          : 'border-slate-800 bg-slate-900 text-slate-400'
                      }`}
                    >
                      {item.actionTag}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
