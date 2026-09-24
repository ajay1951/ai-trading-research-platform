'use client'

import React, { useEffect, useRef } from 'react'
import { Terminal, RefreshCw, Cpu } from 'lucide-react'

interface LiveDaemonLogProps {
  logs?: string[]
  isRefreshing?: boolean
}

export function LiveDaemonLog({ logs = [], isRefreshing = false }: LiveDaemonLogProps) {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [logs])

  return (
    <div className="terminal-card flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/[0.06] bg-slate-950/70 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <Terminal className="size-4 text-emerald-400" />
          <h3 className="font-mono text-xs font-bold text-slate-200 uppercase tracking-wider">
            Live Daemon Log Stream (live_trading.log)
          </h3>
        </div>

        <div className="flex items-center gap-2 font-mono text-[10px] text-slate-400">
          <span className="flex items-center gap-1 text-emerald-400">
            <span className="size-1.5 rounded-full bg-emerald-400 animate-ping" />
            ONLINE
          </span>
          <span className="text-slate-600">|</span>
          <span>{logs.length} EVENTS</span>
        </div>
      </div>

      {/* Terminal Viewport */}
      <div
        ref={scrollRef}
        className="h-[260px] overflow-y-auto bg-[#07090e] p-3 font-mono text-xs leading-relaxed text-slate-300 scrollbar-thin"
      >
        {logs.length === 0 ? (
          <div className="flex h-full items-center justify-center text-slate-500">
            Listening for live daemon execution events...
          </div>
        ) : (
          logs.map((line, idx) => {
            let color = 'text-slate-400'
            if (line.includes('TWAP')) color = 'text-cyan-300 font-semibold'
            else if (line.includes('OPENED') || line.includes('BULL REGIME') || line.includes('COMPLETED')) color = 'text-emerald-400 font-semibold'
            else if (line.includes('BEAR REGIME') || line.includes('SHORT') || line.includes('WARNING') || line.includes('FAILED')) color = 'text-rose-400 font-semibold'
            else if (line.includes('3x MILESTONE')) color = 'text-amber-300 font-bold'

            return (
              <div key={idx} className="py-0.5 whitespace-pre-wrap break-all hover:bg-slate-900/50 px-1 rounded">
                <span className={color}>{line}</span>
              </div>
            )
          })
        )}
        <div className="mt-2 flex items-center gap-1.5 text-emerald-400">
          <span>daemon@nexus-quant:~$</span>
          <span className="inline-block w-2 animate-blink bg-emerald-400">&nbsp;</span>
        </div>
      </div>
    </div>
  )
}
