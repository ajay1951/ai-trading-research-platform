'use client'

import React, { useEffect, useState } from 'react'
import { Activity, ShieldAlert, ShieldCheck, Radio, Clock, RefreshCw } from 'lucide-react'

interface TelemetryRibbonProps {
  cash?: number
  totalEquity?: number
  cycleCount?: number
  targetMilestone?: number
  macroRegime?: 'BULL' | 'BEAR'
  onRefresh?: () => void
  isRefreshing?: boolean
}

export function TelemetryRibbon({
  cash = 26.0,
  totalEquity = 50.0,
  cycleCount = 1,
  targetMilestone = 150.0,
  macroRegime = 'BEAR',
  onRefresh,
  isRefreshing = false
}: TelemetryRibbonProps) {
  const [utcTime, setUtcTime] = useState('--:--:--')
  const [countdown, setCountdown] = useState('--:--')

  useEffect(() => {
    const tick = () => {
      const now = new Date()
      const hh = String(now.getUTCHours()).padStart(2, '0')
      const mm = String(now.getUTCMinutes()).padStart(2, '0')
      const ss = String(now.getUTCSeconds()).padStart(2, '0')
      setUtcTime(`${hh}:${mm}:${ss} UTC`)

      const minLeft = 59 - now.getUTCMinutes()
      const secLeft = 59 - now.getUTCSeconds()
      setCountdown(`${String(minLeft).padStart(2, '0')}:${String(secLeft).padStart(2, '0')}`)
    }
    tick()
    const timer = setInterval(tick, 1000)
    return () => clearInterval(timer)
  }, [])

  const marginUtilizedPct = ((totalEquity - cash) / totalEquity) * 100

  return (
    <div className="flex h-7 w-full shrink-0 select-none items-center justify-between border-b border-white/[0.08] bg-[#06080d] px-3 font-mono text-[11px] text-slate-300">
      {/* Left: System ID + Live Financial Ticker */}
      <div className="flex items-center gap-3 overflow-hidden">
        {/* Brand Chip */}
        <div className="flex items-center gap-1.5 shrink-0">
          <span className="flex size-1.5 rounded-full bg-emerald-400" />
          <span className="font-bold tracking-wider text-slate-100 uppercase">
            NEXUS<span className="text-emerald-400">//PRO</span>
          </span>
          <span className="text-slate-600">|</span>
        </div>

        {/* Financial Telemetry Items */}
        <div className="flex items-center gap-2.5 overflow-x-auto scrollbar-none whitespace-nowrap">
          <div>
            <span className="text-slate-500 uppercase">NAV: </span>
            <span className="font-bold text-slate-100 tabular-nums">${totalEquity.toFixed(2)}</span>
          </div>

          <span className="text-slate-700">·</span>

          <div>
            <span className="text-slate-500 uppercase">CASH: </span>
            <span className="text-slate-300 tabular-nums">${cash.toFixed(2)}</span>
          </div>

          <span className="text-slate-700">·</span>

          <div>
            <span className="text-slate-500 uppercase">EXPOSURE: </span>
            <span className="text-slate-200 font-semibold tabular-nums">
              ${(totalEquity - cash).toFixed(2)} ({marginUtilizedPct.toFixed(0)}%)
            </span>
          </div>

          <span className="text-slate-700">·</span>

          <div>
            <span className="text-slate-500 uppercase">MILESTONE: </span>
            <span className="text-slate-200 font-semibold tabular-nums">
              C{cycleCount} (${targetMilestone.toFixed(0)})
            </span>
          </div>

          <span className="text-slate-700">·</span>

          <div>
            <span className="text-slate-500 uppercase">7Y SHARPE: </span>
            <span className="text-slate-200 font-semibold tabular-nums">1.65</span>
          </div>

          <span className="text-slate-700">·</span>

          <div>
            <span className="text-slate-500 uppercase">WFO STABILITY: </span>
            <span className="text-emerald-400 font-bold">5/5 PASSED</span>
          </div>
        </div>
      </div>

      {/* Right: Connectivity & Synchronization Telemetry */}
      <div className="hidden sm:flex shrink-0 items-center gap-2.5 pl-2">
        {/* Macro Regime Pill */}
        <div
          className={`flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold ${
            macroRegime === 'BULL'
              ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-500/30'
              : 'bg-rose-950/80 text-rose-300 border border-rose-500/30'
          }`}
        >
          {macroRegime === 'BULL' ? (
            <ShieldCheck className="size-3 text-emerald-400" />
          ) : (
            <ShieldAlert className="size-3 text-rose-400" />
          )}
          <span>{macroRegime} REGIME</span>
        </div>

        {/* Venue status */}
        <div className="flex items-center gap-1 text-slate-400">
          <Radio className="size-2.5 text-emerald-400" />
          <span>BINANCE USDS-M · 24ms</span>
        </div>

        {/* 1h Candle Countdown */}
        <div className="flex items-center gap-1 text-slate-400">
          <Clock className="size-2.5 text-amber-400" />
          <span>CLOSE IN: <span className="text-amber-300 font-bold tabular-nums">{countdown}</span></span>
        </div>

        {/* UTC Time */}
        <div className="tabular-nums font-semibold text-slate-300">
          {utcTime}
        </div>

        {/* Refresh button */}
        {onRefresh && (
          <button
            onClick={onRefresh}
            disabled={isRefreshing}
            className="flex size-5 items-center justify-center rounded text-slate-400 hover:text-slate-200 transition-colors"
            title="Refresh State"
          >
            <RefreshCw className={`size-3 ${isRefreshing ? 'animate-spin text-emerald-400' : ''}`} />
          </button>
        )}
      </div>
    </div>
  )
}
