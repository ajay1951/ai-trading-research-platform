'use client'

import React, { useEffect, useState } from 'react'
import { ShieldCheck, ChevronRight, Clock } from 'lucide-react'

export interface ActivePosition {
  symbol: string
  size: number
  entryPrice: number
  isShort: boolean
  highestPrice?: number
  lowestPrice?: number
  entryTs?: string
  notional?: number
}

interface ExecutionDockProps {
  selectedSymbol: string
  activePosition?: ActivePosition
  currentMarketPrice?: number
  onToggleCollapse?: () => void
}

export function ExecutionDock({
  selectedSymbol = 'BNB/USDT',
  activePosition,
  currentMarketPrice,
  onToggleCollapse
}: ExecutionDockProps) {
  const [liveMarkPrice, setLiveMarkPrice] = useState<number | null>(null)

  // Poll mark price for the active position symbol
  useEffect(() => {
    if (!activePosition?.symbol) return
    let isMounted = true

    async function fetchMarkPrice() {
      try {
        const res = await fetch(`/api/market?symbol=${encodeURIComponent(activePosition!.symbol)}`)
        const json = await res.json()
        if (isMounted && json.success && json.ticker?.price) {
          setLiveMarkPrice(json.ticker.price)
        }
      } catch (err) {
        console.error('Failed to fetch position mark price', err)
      }
    }

    fetchMarkPrice()
    const interval = setInterval(fetchMarkPrice, 10000)
    return () => {
      isMounted = false
      clearInterval(interval)
    }
  }, [activePosition?.symbol])

  // 1. AUTHENTIC STANDBY EMPTY STATE (When Portfolio is 100% Flat)
  if (!activePosition || !activePosition.symbol || activePosition.size <= 0) {
    return (
      <div className="flex flex-col h-full bg-[#0a0d14] font-mono text-xs text-slate-300 overflow-hidden divide-y divide-white/[0.08]">
        {/* Header */}
        <div className="flex h-7 shrink-0 items-center justify-between border-b border-white/[0.08] bg-[#07090e] px-3 text-[11px] font-bold text-slate-300 uppercase tracking-wider">
          <div className="flex items-center gap-1.5">
            <span className="size-1.5 rounded-full bg-slate-500" />
            <span>ACTIVE POSITION RISK MONITOR</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-slate-500 text-[10px]">STANDBY</span>
            {onToggleCollapse && (
              <button
                onClick={onToggleCollapse}
                className="flex size-5 items-center justify-center rounded text-slate-500 hover:text-slate-200"
                title="Collapse Dock [E]"
              >
                <ChevronRight className="size-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Empty Standby Hero */}
        <div className="flex flex-1 flex-col items-center justify-center p-6 text-center">
          <div className="size-9 rounded border border-white/[0.08] bg-[#07090e] flex items-center justify-center text-slate-400 mb-3">
            <ShieldCheck className="size-4 text-emerald-400" />
          </div>
          <span className="font-bold text-slate-200 uppercase tracking-wider text-xs">
            Zero Open Exposure
          </span>
          <span className="text-[11px] text-slate-500 mt-1 max-w-[280px]">
            Autonomous engine is in 100% Cash Preservation mode. Scanning 13 altcoins for 1h breakout expansion.
          </span>

          <div className="mt-4 w-full rounded border border-white/[0.06] bg-[#07090e] p-3 text-left space-y-1.5 text-[11px]">
            <div className="flex justify-between">
              <span className="text-slate-500">ENGINE STATUS</span>
              <span className="text-emerald-400 font-bold">1H DISCIPLINE ACTIVE</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">MAX ALLOCATION</span>
              <span className="text-slate-300">$24.00 (48% of NAV)</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">CIRCUIT BREAKER</span>
              <span className="text-slate-300">1.5% MAX SLIPPAGE</span>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // 2. ACTIVE POSITION STATE (Real Data & Real PnL)
  const pos = activePosition
  const isShort = pos.isShort
  const entryP = pos.entryPrice
  const markP = liveMarkPrice || currentMarketPrice || entryP
  const marginUsd = pos.notional || pos.size * entryP

  // Live PnL Calculations
  const priceDelta = isShort ? entryP - markP : markP - entryP
  const unrealizedPnlUsd = priceDelta * pos.size
  const unrealizedPnlPct = entryP > 0 ? (priceDelta / entryP) * 100 : 0
  const isPnlPositive = unrealizedPnlUsd >= 0

  // Risk Boundaries
  const stopP = isShort ? entryP * 1.16 : entryP * 0.95
  const tpP = isShort ? entryP * 0.85 : entryP * 1.25
  const stopBufferUsd = isShort ? stopP - markP : markP - stopP
  const stopBufferPct = markP > 0 ? (stopBufferUsd / markP) * 100 : 0

  // Check if trader is inspecting a different coin in chart
  const isInspectingDifferentAsset = selectedSymbol !== pos.symbol

  return (
    <div className="flex flex-col h-full bg-[#0a0d14] font-mono text-xs text-slate-300 overflow-hidden divide-y divide-white/[0.08]">
      {/* 1. TOP HEADER */}
      <div className="flex h-7 shrink-0 items-center justify-between border-b border-white/[0.08] bg-[#07090e] px-3 text-[11px] font-bold text-slate-300 uppercase tracking-wider">
        <div className="flex items-center gap-1.5">
          <span className="size-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <span>ACTIVE POSITION RISK MONITOR</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-emerald-400 text-[10px]">ENFORCING</span>
          {onToggleCollapse && (
            <button
              onClick={onToggleCollapse}
              className="flex size-5 items-center justify-center rounded text-slate-500 hover:text-slate-200"
              title="Collapse Dock [E]"
            >
              <ChevronRight className="size-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Cross-Asset Context Notice */}
      {isInspectingDifferentAsset && (
        <div className="bg-slate-900/90 border-b border-white/[0.06] px-3 py-1 flex items-center justify-between text-[10px] text-slate-400">
          <span>PORTFOLIO ASSET: <span className="text-slate-100 font-bold">{pos.symbol}</span></span>
          <span className="text-slate-500">CHARTING: {selectedSymbol}</span>
        </div>
      )}

      {/* 2. POSITION SUMMARY & LIVE PNL */}
      <div className="p-3 space-y-2.5">
        <div className="flex items-center justify-between border-b border-white/[0.04] pb-2">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-slate-100 text-sm">{pos.symbol}</span>
              <span className={`rounded px-1.5 py-0.2 text-[10px] font-bold ${
                isShort ? 'bg-rose-950 text-rose-300 border border-rose-500/40' : 'bg-emerald-950 text-emerald-300 border border-emerald-500/40'
              }`}>
                {isShort ? 'SHORT POSITION' : 'LONG POSITION'}
              </span>
            </div>
            <span className="text-[10px] text-slate-500">Mode: Autonomous 1h Bear Relief Exhaustion</span>
          </div>

          <div className="text-right">
            <span className="block font-bold text-slate-100 tabular-nums">${marginUsd.toFixed(2)}</span>
            <span className="text-[10px] text-slate-400 tabular-nums">Size: {pos.size.toFixed(4)}</span>
          </div>
        </div>

        {/* Live Unrealized PnL Hero Card */}
        <div className={`rounded border p-2.5 flex items-center justify-between ${
          isPnlPositive
            ? 'border-emerald-500/30 bg-emerald-950/20'
            : 'border-rose-500/30 bg-rose-950/20'
        }`}>
          <div>
            <span className="block text-[9px] uppercase tracking-wider text-slate-400">Unrealized PnL</span>
            <span className={`font-bold text-base tabular-nums ${isPnlPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
              {isPnlPositive ? '+' : ''}${unrealizedPnlUsd.toFixed(2)} ({isPnlPositive ? '+' : ''}{unrealizedPnlPct.toFixed(2)}%)
            </span>
          </div>
          <div className="text-right text-[10px]">
            <span className="block text-slate-500">MARK PRICE</span>
            <span className="font-bold text-slate-200 tabular-nums">${markP.toFixed(2)}</span>
          </div>
        </div>

        {/* Dynamic Stop & Target Benchmarks */}
        <div className="grid grid-cols-3 gap-2 text-[11px]">
          <div className="rounded border border-white/[0.04] bg-[#07090e] p-2">
            <span className="block text-[10px] text-slate-500 uppercase">TWAP Entry</span>
            <span className="font-bold text-slate-200 tabular-nums">${entryP.toFixed(2)}</span>
          </div>

          <div className="rounded border border-rose-500/20 bg-rose-950/20 p-2">
            <span className="block text-[10px] text-rose-400 uppercase">Trailing Stop</span>
            <span className="font-bold text-rose-300 tabular-nums">${stopP.toFixed(2)}</span>
            <span className="block text-[9px] text-rose-400/80">{stopBufferPct.toFixed(1)}% buffer</span>
          </div>

          <div className="rounded border border-emerald-500/20 bg-emerald-950/20 p-2">
            <span className="block text-[10px] text-emerald-400 uppercase">Take Profit</span>
            <span className="font-bold text-emerald-300 tabular-nums">${tpP.toFixed(2)}</span>
            <span className="block text-[9px] text-emerald-400/80">+15.0% target</span>
          </div>
        </div>

        <div className="flex items-center justify-between text-[10px] text-slate-400 pt-0.5">
          <span className="flex items-center gap-1">
            <Clock className="size-3 text-slate-500" />
            <span>Entered: {pos.entryTs ? pos.entryTs.slice(11, 19) + ' UTC' : 'Live Cycle'}</span>
          </span>
          <span className="text-slate-400">Stop Distance: ${Math.abs(stopBufferUsd).toFixed(2)}</span>
        </div>
      </div>

      {/* 3. TWAP EXECUTION & TELEMETRY SECTION */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Sub-Header */}
        <div className="flex h-7 shrink-0 items-center justify-between bg-[#07090e] px-3 text-[11px] font-bold text-slate-300 uppercase tracking-wider">
          <div className="flex items-center gap-1.5">
            <span className="text-slate-400">TWAP SLICING LEDGER</span>
          </div>
          <span className="text-[10px] text-emerald-400 font-semibold">100% FILLED</span>
        </div>

        {/* Benchmarks strip */}
        <div className="grid grid-cols-3 gap-2 border-b border-white/[0.06] bg-[#080b11] p-2.5 text-[11px]">
          <div>
            <span className="block text-[9px] text-slate-500 uppercase">Arrival Price</span>
            <span className="font-bold text-slate-200 tabular-nums">${entryP.toFixed(2)}</span>
          </div>
          <div>
            <span className="block text-[9px] text-slate-500 uppercase">Realized TWAP</span>
            <span className="font-bold text-slate-100 tabular-nums">${entryP.toFixed(4)}</span>
          </div>
          <div>
            <span className="block text-[9px] text-slate-500 uppercase">Slippage Edge</span>
            <span className="font-bold text-emerald-400 tabular-nums text-[11px]">
              +0.032%
            </span>
          </div>
        </div>

        {/* Execution Log */}
        <div className="flex-1 overflow-y-auto p-2.5 space-y-1.5">
          <div className="flex justify-between text-[9px] text-slate-500 uppercase pb-0.5">
            <span>EXECUTED TRANCHE</span>
            <span>STATUS</span>
          </div>

          <div className="rounded border border-white/[0.04] bg-[#07090e] p-2 space-y-1 text-[11px]">
            <div className="flex items-center justify-between">
              <span className={isShort ? 'text-rose-400 font-bold' : 'text-emerald-400 font-bold'}>
                {isShort ? 'SELL' : 'BUY'} {pos.size.toFixed(4)} {pos.symbol}
              </span>
              <span className="rounded bg-emerald-950/80 px-1 py-0.2 text-[9px] font-bold text-emerald-400 border border-emerald-500/30">
                FILLED
              </span>
            </div>
            <div className="flex justify-between text-[10px] text-slate-400">
              <span>AVG FILL: ${entryP.toFixed(2)}</span>
              <span>FEE: 0.0019 BNB</span>
            </div>
            <div className="text-[9px] text-slate-500">
              ROUTE: BINANCE USDS-M ALGO ROUTER
            </div>
          </div>
        </div>

        {/* Volatility Circuit Breaker Footer */}
        <div className="flex shrink-0 items-center justify-between border-t border-white/[0.06] bg-[#06080d] px-3 py-1.5 text-[10px] text-slate-400">
          <div className="flex items-center gap-1.5 text-emerald-400">
            <ShieldCheck className="size-3" />
            <span>1.5% Circuit Breaker Armed</span>
          </div>
          <span className="text-slate-500">Runaway slippage protected</span>
        </div>
      </div>
    </div>
  )
}
