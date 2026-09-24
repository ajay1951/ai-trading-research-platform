'use client'

import React, { useState, useEffect, useRef } from 'react'
import { TelemetryRibbon } from './telemetry-ribbon'
import { ChartDesk } from './chart-desk'
import { ExecutionDock } from './execution-dock'
import { TradeBlotter } from './trade-blotter'
import { ScreenerMatrix } from './screener-matrix'
import { WfoAuditCard } from './wfo-audit-card'
import { LiveDaemonLog } from './live-daemon-log'
import { StatusBar } from './status-bar'

type BottomDockTab = 'BLOTTER' | 'SCREENER' | 'WFO' | 'LOGS'

export function TradingDashboard() {
  const [state, setState] = useState<any>(null)
  const [selectedSymbol, setSelectedSymbol] = useState<string>('BNB/USDT')
  const [bottomTab, setBottomTab] = useState<BottomDockTab>('BLOTTER')
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [latencyMs, setLatencyMs] = useState(24)
  const [isDockCollapsed, setIsDockCollapsed] = useState(false)
  const hasUserSelectedRef = useRef(false)

  const handleSelectSymbol = (sym: string) => {
    hasUserSelectedRef.current = true
    setSelectedSymbol(sym)
  }

  async function fetchState(isInitial = false) {
    try {
      setIsRefreshing(true)
      const t0 = performance.now()
      const res = await fetch('/api/state')
      const json = await res.json()
      const rtt = Math.round(performance.now() - t0)
      if (rtt > 0) setLatencyMs(rtt)

      if (json.success) {
        setState(json)
        if (isInitial && !hasUserSelectedRef.current && json.positions && json.positions.length > 0) {
          const activeSym = json.positions[0].symbol
          if (activeSym) setSelectedSymbol(activeSym)
        }
      }
    } catch (err) {
      console.error('Failed to fetch daemon state', err)
    } finally {
      setIsRefreshing(false)
    }
  }

  useEffect(() => {
    fetchState(true)
    const interval = setInterval(() => fetchState(false), 10000)
    return () => clearInterval(interval)
  }, [])

  // Keyboard Hotkeys Ergonomics
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement)?.tagName)) return

      const key = e.key
      if (key === '1') setBottomTab('BLOTTER')
      else if (key === '2') setBottomTab('SCREENER')
      else if (key === '3') setBottomTab('WFO')
      else if (key === '4') setBottomTab('LOGS')
      else if (key === 'e' || key === 'E') setIsDockCollapsed(prev => !prev)
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  const macroRegime = 'BEAR'
  const activePositions: any[] = state?.positions || []

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-[#07090e] font-sans antialiased select-none">
      {/* 1. Docked Telemetry Ribbon (28px) */}
      <TelemetryRibbon
        cash={state?.cash ?? 26.0}
        totalEquity={state?.totalEquity ?? 50.0}
        cycleCount={state?.cycleCount ?? 1}
        targetMilestone={state?.targetMilestone ?? 150.0}
        macroRegime={macroRegime}
        onRefresh={() => fetchState(false)}
        isRefreshing={isRefreshing}
      />

      {/* 2. Primary Workspace (Split Grid, zero gap) */}
      <div className="flex flex-1 min-w-0 min-h-0 overflow-hidden">
        {/* Left Pane (Full or 68% width): Interactive Chart Desk */}
        <div className="flex flex-1 min-w-0 min-h-0 flex-col border-r border-white/[0.08] overflow-hidden">
          <ChartDesk
            selectedSymbol={selectedSymbol}
            onSelectSymbol={handleSelectSymbol}
            activePositions={activePositions}
          />
        </div>

        {/* Right Pane (Collapsible 390px): Autonomous Execution & Risk Telemetry Dock */}
        {!isDockCollapsed ? (
          <div className="flex w-[390px] shrink-0 flex-col overflow-hidden bg-[#0a0d14]">
            <ExecutionDock
              selectedSymbol={selectedSymbol}
              activePosition={activePositions[0]}
              onToggleCollapse={() => setIsDockCollapsed(true)}
            />
          </div>
        ) : (
          <div className="flex w-6 shrink-0 flex-col items-center justify-between border-l border-white/[0.08] bg-[#07090e] py-3">
            <button
              onClick={() => setIsDockCollapsed(false)}
              className="flex flex-col items-center gap-1 font-mono text-[9px] font-bold text-slate-500 hover:text-emerald-400 transition-colors"
              title="Expand Risk Dock [E]"
            >
              <span className="rotate-90 whitespace-nowrap tracking-wider">RISK DOCK [E]</span>
            </button>
          </div>
        )}
      </div>

      {/* 3. Bottom Operations Dock (35% fixed height, border-t) */}
      <div className="flex h-[280px] shrink-0 flex-col border-t border-white/[0.08] bg-[#0a0d14] overflow-hidden">
        {/* Docked Tab Header */}
        <div className="flex h-7 shrink-0 items-center justify-between border-b border-white/[0.08] bg-[#07090e] px-2 font-mono text-[11px]">
          <div className="flex items-center gap-1">
            <button
              onClick={() => setBottomTab('BLOTTER')}
              className={`px-3 py-1 font-bold transition-colors ${
                bottomTab === 'BLOTTER'
                  ? 'border-b-2 border-emerald-400 text-slate-100 bg-[#0d1118]'
                  : 'text-slate-500 hover:text-slate-200 hover:bg-white/[0.02]'
              }`}
            >
              <span>[1] BLOTTER (2,331 FILLS)</span>
            </button>

            <button
              onClick={() => setBottomTab('SCREENER')}
              className={`px-3 py-1 font-bold transition-colors ${
                bottomTab === 'SCREENER'
                  ? 'border-b-2 border-emerald-400 text-slate-100 bg-[#0d1118]'
                  : 'text-slate-500 hover:text-slate-200 hover:bg-white/[0.02]'
              }`}
            >
              <span>[2] MOMENTUM SCREENER (13 COINS)</span>
            </button>

            <button
              onClick={() => setBottomTab('WFO')}
              className={`px-3 py-1 font-bold transition-colors ${
                bottomTab === 'WFO'
                  ? 'border-b-2 border-emerald-400 text-slate-100 bg-[#0d1118]'
                  : 'text-slate-500 hover:text-slate-200 hover:bg-white/[0.02]'
              }`}
            >
              <span>[3] WFO AUDIT (5 FOLDS)</span>
            </button>

            <button
              onClick={() => setBottomTab('LOGS')}
              className={`px-3 py-1 font-bold transition-colors ${
                bottomTab === 'LOGS'
                  ? 'border-b-2 border-emerald-400 text-slate-100 bg-[#0d1118]'
                  : 'text-slate-500 hover:text-slate-200 hover:bg-white/[0.02]'
              }`}
            >
              <span>[4] DAEMON LOGS</span>
            </button>
          </div>

          <span className="hidden sm:block font-mono text-[10px] text-slate-500">
            PRESS [1-4] TO SWITCH DOCKS
          </span>
        </div>

        {/* Tab Content Display */}
        <div className="flex-1 overflow-hidden">
          {bottomTab === 'BLOTTER' && <TradeBlotter />}
          {bottomTab === 'SCREENER' && <ScreenerMatrix onSelectSymbol={handleSelectSymbol} />}
          {bottomTab === 'WFO' && <WfoAuditCard />}
          {bottomTab === 'LOGS' && <LiveDaemonLog logs={state?.recentLogs || []} isRefreshing={isRefreshing} />}
        </div>
      </div>

      {/* 4. Pinned Bottom Micro Status Bar (22px) */}
      <StatusBar macroRegime={macroRegime} rtt={latencyMs} />
    </div>
  )
}
