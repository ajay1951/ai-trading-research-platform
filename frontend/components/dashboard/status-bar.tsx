'use client'

import React from 'react'
import { Radio, Keyboard } from 'lucide-react'

export function StatusBar({
  macroRegime = 'BEAR',
  rtt = 24
}: {
  macroRegime?: 'BULL' | 'BEAR'
  rtt?: number
}) {
  return (
    <div className="flex h-[22px] w-full shrink-0 select-none items-center justify-between border-t border-white/[0.08] bg-[#05070a] px-3 font-mono text-[10px] text-slate-400">
      {/* Left: Execution status */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5">
          <span className="size-1.5 rounded-full bg-emerald-400" />
          <span className="text-slate-300 font-semibold">ENGINE: AUTONOMOUS CANDLE-CLOSE SYNC</span>
        </div>
        <span className="text-slate-700">|</span>
        <span className="text-slate-400">1H BAR DISCIPLINE</span>
      </div>

      {/* Center: Macro Regime & Hotkeys */}
      <div className="hidden md:flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <span className="text-slate-500">MACRO:</span>
          <span className={macroRegime === 'BULL' ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
            {macroRegime} REGIME (BTC {macroRegime === 'BULL' ? '> 100d' : '< 100d'})
          </span>
        </div>

        <span className="text-slate-700">|</span>

        <div className="flex items-center gap-1.5 text-slate-500">
          <Keyboard className="size-3 text-slate-400" />
          <span>HOTKEYS:</span>
          <span className="text-slate-300 font-semibold">[1-4] DOCKS</span>
          <span className="text-slate-300 font-semibold">[E] DOCK</span>
          <span className="text-slate-300 font-semibold">[/] SEARCH</span>
          <span className="text-slate-300 font-semibold">[ESC] RESET</span>
        </div>
      </div>

      {/* Right: Latency & Frame Telemetry */}
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1 text-slate-400">
          <Radio className="size-2.5 text-emerald-400" />
          <span>RTT: <span className="text-slate-200 font-bold tabular-nums">{rtt}ms</span></span>
        </div>
        <span className="text-slate-700">|</span>
        <span className="text-emerald-400 font-semibold">0 TICKS DROPPED</span>
      </div>
    </div>
  )
}
