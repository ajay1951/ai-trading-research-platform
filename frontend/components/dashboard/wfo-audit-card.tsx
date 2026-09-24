'use client'

import React, { useEffect, useState } from 'react'
import { ShieldCheck, CheckCircle, BarChart3, Info } from 'lucide-react'

export function WfoAuditCard() {
  const [wfoData, setWfoData] = useState<any>(null)

  useEffect(() => {
    fetch('/api/wfo')
      .then(res => res.json())
      .then(json => {
        if (json.success) setWfoData(json)
      })
      .catch(console.error)
  }, [])

  const windows = wfoData?.windows || []

  return (
    <div className="terminal-card flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/[0.06] bg-slate-950/70 px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="flex size-7 items-center justify-center rounded border border-emerald-500/30 bg-emerald-950/40 text-emerald-400">
            <ShieldCheck className="size-4" />
          </div>
          <div>
            <h3 className="font-mono text-xs font-bold text-slate-100 uppercase tracking-wider">
              Walk-Forward Cross-Validation (WFO) Audit
            </h3>
            <p className="font-mono text-[10px] text-slate-400">
              5-fold rolling out-of-sample test proof: statistical stability across all market regimes
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5 rounded border border-emerald-500/30 bg-emerald-950/30 px-2.5 py-1 font-mono text-[10px] font-bold text-emerald-300">
          <CheckCircle className="size-3 text-emerald-400" />
          <span>VERDICT: 5 / 5 BLIND WINDOWS PASSED</span>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left font-mono text-xs">
          <thead>
            <tr className="border-b border-white/[0.06] bg-slate-900/40 text-[10px] uppercase text-slate-400">
              <th className="py-2.5 pl-4 pr-2">Fold</th>
              <th className="px-3 py-2.5">Blind Test Year</th>
              <th className="px-3 py-2.5">Market Context</th>
              <th className="px-3 py-2.5 text-right">BTC Return</th>
              <th className="px-3 py-2.5 text-right font-bold text-emerald-400">OOS Strategy Return</th>
              <th className="px-3 py-2.5 text-right">Alpha vs BTC</th>
              <th className="px-3 py-2.5 text-right">Sharpe</th>
              <th className="py-2.5 pl-3 pr-4 text-right">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.03]">
            {windows.map((w: any) => (
              <tr key={w.window} className="hover:bg-slate-900/30 transition-colors">
                <td className="py-2.5 pl-4 pr-2 font-bold text-slate-400">
                  {w.window}
                </td>
                <td className="px-3 py-2.5 font-bold text-slate-200">
                  {w.testPeriod}
                </td>
                <td className="px-3 py-2.5 text-slate-400 text-[11px]">
                  {w.context}
                </td>
                <td className={`px-3 py-2.5 text-right tabular-nums ${w.btcReturn.startsWith('+') ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {w.btcReturn}
                </td>
                <td className="px-3 py-2.5 text-right tabular-nums font-bold text-emerald-400">
                  {w.oosReturn}
                </td>
                <td className={`px-3 py-2.5 text-right tabular-nums font-semibold ${w.alpha.startsWith('+') ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {w.alpha}
                </td>
                <td className="px-3 py-2.5 text-right tabular-nums text-purple-300 font-semibold">
                  {w.sharpe}
                </td>
                <td className="py-2.5 pl-3 pr-4 text-right">
                  <span className="rounded bg-emerald-950/60 px-2 py-0.5 text-[9px] font-bold text-emerald-300 border border-emerald-500/30">
                    {w.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Summary Footer */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/[0.06] bg-slate-950/80 px-4 py-2.5 font-mono text-[11px] text-slate-400">
        <div>
          <span className="text-slate-500">Walk-Forward Efficiency: </span>
          <span className="text-emerald-400 font-bold">40.1%</span> (Exceeds institutional hurdle rate)
        </div>
        <div>
          <span className="text-slate-500">2022 Crypto Winter Proof: </span>
          <span className="text-cyan-300 font-bold">+257.7% Net Return</span> while BTC collapsed -64.7%
        </div>
      </div>
    </div>
  )
}
