'use client'

import React, { useEffect, useRef, useState } from 'react'
import { createChart, IChartApi, ISeriesApi } from 'lightweight-charts'

const UNIVERSE_SYMBOLS = [
  'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT',
  'DOGE/USDT', 'ADA/USDT', 'AVAX/USDT', 'LINK/USDT', 'NEAR/USDT',
  'LTC/USDT', 'DOT/USDT', 'SUI/USDT'
]

interface ActivePosition {
  symbol: string
  size: number
  entryPrice: number
  isShort: boolean
  highestPrice?: number
  lowestPrice?: number
}

interface ChartDeskProps {
  selectedSymbol: string
  onSelectSymbol: (sym: string) => void
  activePositions?: ActivePosition[]
}

export function ChartDesk({
  selectedSymbol = 'BNB/USDT',
  onSelectSymbol,
  activePositions = []
}: ChartDeskProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartInstanceRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<any>(null)
  const volumeSeriesRef = useRef<any>(null)
  const priceLinesRef = useRef<any[]>([])

  const [marketData, setMarketData] = useState<any>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [timeframe, setTimeframe] = useState<'1h' | '4h' | '1d'>('1h')

  // Check if current asset has an active position
  const currentPos = activePositions.find(p => p.symbol === selectedSymbol)

  useEffect(() => {
    let isMounted = true
    setIsLoading(true)

    async function loadKlines() {
      try {
        const res = await fetch(`/api/market?symbol=${encodeURIComponent(selectedSymbol)}`)
        const json = await res.json()
        if (isMounted && json.success && json.klines) {
          setMarketData(json)
        }
      } catch (err) {
        console.error('Failed to load market klines', err)
      } finally {
        if (isMounted) setIsLoading(false)
      }
    }

    loadKlines()
    const interval = setInterval(loadKlines, 15000)
    return () => {
      isMounted = false
      clearInterval(interval)
    }
  }, [selectedSymbol, timeframe])

  // 1. Chart Instance Lifecycle & Responsive ResizeObserver
  useEffect(() => {
    if (!chartContainerRef.current) return

    const container = containerRef.current || chartContainerRef.current
    const initialWidth = Math.max(container.clientWidth || 800, 200)
    const initialHeight = Math.max(container.clientHeight || 450, 200)

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: 'solid', color: '#090d14' },
        textColor: '#94a3b8',
        fontSize: 11,
        fontFamily: 'monospace'
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.03)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.03)' }
      },
      crosshair: {
        mode: 1,
        vertLine: { color: 'rgba(255, 255, 255, 0.2)', width: 1, style: 2 },
        horzLine: { color: 'rgba(255, 255, 255, 0.2)', width: 1, style: 2 }
      },
      timeScale: {
        borderColor: 'rgba(255, 255, 255, 0.08)',
        timeVisible: true,
        secondsVisible: false
      },
      rightPriceScale: {
        visible: true,
        borderColor: 'rgba(255, 255, 255, 0.12)',
        entireTextOnly: true,
        autoScale: true,
        scaleMargins: { top: 0.08, bottom: 0.2 }
      },
      width: initialWidth,
      height: initialHeight
    })

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444'
    })

    const volumeSeries = chart.addHistogramSeries({
      color: '#26a69a',
      priceFormat: { type: 'volume' },
      priceScaleId: '',
      scaleMargins: { top: 0.82, bottom: 0 }
    })

    chartInstanceRef.current = chart
    candleSeriesRef.current = candleSeries
    volumeSeriesRef.current = volumeSeries

    // Responsive sizing via ResizeObserver
    const resizeObserver = new ResizeObserver(entries => {
      if (!entries || !entries[0] || !chartInstanceRef.current) return
      const { width, height } = entries[0].contentRect
      if (width > 50 && height > 50) {
        chartInstanceRef.current.applyOptions({
          width: Math.floor(width),
          height: Math.floor(height)
        })
      }
    })

    if (containerRef.current) {
      resizeObserver.observe(containerRef.current)
    }

    return () => {
      resizeObserver.disconnect()
      chart.remove()
      chartInstanceRef.current = null
      candleSeriesRef.current = null
      volumeSeriesRef.current = null
      priceLinesRef.current = []
    }
  }, [])

  // 2. Data & Price Lines Update
  useEffect(() => {
    if (!candleSeriesRef.current || !chartInstanceRef.current) return

    if (marketData && marketData.klines) {
      const sortedKlines = [...marketData.klines].sort((a, b) => a.time - b.time)
      const uniqueKlines: any[] = []
      const seenTimes = new Set()
      for (const k of sortedKlines) {
        if (!seenTimes.has(k.time)) {
          seenTimes.add(k.time)
          uniqueKlines.push(k)
        }
      }

      candleSeriesRef.current.setData(uniqueKlines)

      if (volumeSeriesRef.current) {
        const volData = uniqueKlines.map(k => ({
          time: k.time,
          value: k.volume || 0,
          color: k.close >= k.open ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'
        }))
        volumeSeriesRef.current.setData(volData)
      }

      // Remove previous price lines before redrawing
      if (priceLinesRef.current.length > 0) {
        priceLinesRef.current.forEach(line => {
          try {
            candleSeriesRef.current?.removePriceLine(line)
          } catch {}
        })
        priceLinesRef.current = []
      }

      // Add active position price lines only if the selected symbol has an active position
      if (currentPos && currentPos.entryPrice > 0) {
        const entryLine = candleSeriesRef.current.createPriceLine({
          price: currentPos.entryPrice,
          color: currentPos.isShort ? '#ef4444' : '#10b981',
          lineWidth: 2,
          lineStyle: 0,
          axisLabelVisible: true,
          title: `ENTRY: $${currentPos.entryPrice.toFixed(2)} (${currentPos.isShort ? 'SHORT' : 'LONG'})`
        })
        priceLinesRef.current.push(entryLine)

        // Trailing stop line
        if (currentPos.isShort) {
          const stopP = currentPos.entryPrice * 1.16
          const stopLine = candleSeriesRef.current.createPriceLine({
            price: stopP,
            color: '#f59e0b',
            lineWidth: 1,
            lineStyle: 2,
            axisLabelVisible: true,
            title: `TRAIL STOP: $${stopP.toFixed(2)} (-16%)`
          })
          priceLinesRef.current.push(stopLine)

          const tpP = currentPos.entryPrice * 0.85
          const tpLine = candleSeriesRef.current.createPriceLine({
            price: tpP,
            color: '#10b981',
            lineWidth: 1,
            lineStyle: 2,
            axisLabelVisible: true,
            title: `TARGET TP: $${tpP.toFixed(2)} (+15%)`
          })
          priceLinesRef.current.push(tpLine)
        }
      }

      chartInstanceRef.current.timeScale().fitContent()
    }
  }, [marketData, currentPos])

  const ticker = marketData?.ticker
  const isPositive = (ticker?.change24h || 0) >= 0

  return (
    <div className="flex flex-col h-full w-full min-w-0 min-h-0 bg-[#090d14] overflow-hidden">
      {/* 1. Universe Symbol Bar */}
      <div className="flex h-7 shrink-0 items-center gap-1 overflow-x-auto border-b border-white/[0.08] bg-[#07090e] px-2 scrollbar-none">
        <span className="shrink-0 px-1 font-mono text-[9px] font-bold text-slate-500 uppercase tracking-wider">
          UNIVERSE:
        </span>
        {UNIVERSE_SYMBOLS.map(sym => {
          const isSelected = sym === selectedSymbol
          const hasPos = activePositions.some(p => p.symbol === sym)
          return (
            <button
              key={sym}
              onClick={() => onSelectSymbol(sym)}
              className={`flex shrink-0 items-center gap-1.5 rounded px-2.5 py-1 font-mono text-xs transition-all ${
                isSelected
                  ? 'border border-emerald-500/40 bg-emerald-950/40 text-emerald-300 font-semibold shadow-sm'
                  : 'border border-slate-800/60 bg-slate-900/40 text-slate-400 hover:text-slate-200 hover:border-slate-700'
              }`}
            >
              {hasPos && <span className="size-1.5 rounded-full bg-amber-400 animate-pulse" />}
              <span>{sym.replace('/USDT', '')}</span>
            </button>
          )
        })}
      </div>

      {/* 2. Chart Instrument Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.06] bg-slate-900/40 px-4 py-2.5">
        <div className="flex items-center gap-3">
          <div className="font-mono">
            <div className="flex items-baseline gap-2">
              <span className="text-lg font-bold text-slate-100">{selectedSymbol}</span>
              <span className="text-xs font-semibold text-slate-400">1H PERP</span>
              {currentPos && (
                <span className="rounded bg-amber-950/60 border border-amber-500/40 px-2 py-0.5 text-[10px] font-bold text-amber-300 uppercase tracking-wide">
                  ACTIVE {currentPos.isShort ? 'SHORT' : 'LONG'} (SIZE: {currentPos.size.toFixed(4)})
                </span>
              )}
            </div>
            <div className="flex items-center gap-3 text-xs text-slate-400">
              <span className="text-slate-100 font-bold tabular-nums text-base">
                ${ticker?.price ? ticker.price.toFixed(ticker.price < 2 ? 4 : 2) : '---'}
              </span>
              <span className={`flex items-center font-semibold tabular-nums ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
                {isPositive ? '+' : ''}{ticker?.change24h?.toFixed(2)}% (24h)
              </span>
            </div>
          </div>
        </div>

        {/* 24h Stats & Timeframe controls */}
        <div className="flex items-center gap-4">
          <div className="hidden sm:flex items-center gap-4 font-mono text-[11px] text-slate-400">
            <div>
              <span className="text-slate-500">24h High: </span>
              <span className="tabular-nums text-slate-200 font-medium">${ticker?.high24h?.toFixed(2) || '---'}</span>
            </div>
            <div>
              <span className="text-slate-500">24h Low: </span>
              <span className="tabular-nums text-slate-200 font-medium">${ticker?.low24h?.toFixed(2) || '---'}</span>
            </div>
            <div>
              <span className="text-slate-500">Source: </span>
              <span className="text-emerald-400 font-medium">{marketData?.source === 'BINANCE_LIVE' ? 'Binance Public REST (15s Sync)' : 'Historical Cache'}</span>
            </div>
          </div>

          <div className="flex rounded border border-slate-800 bg-slate-950 p-0.5 font-mono text-xs">
            {(['1h', '4h', '1d'] as const).map(tf => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`px-2 py-0.5 rounded text-[11px] font-semibold transition-colors ${
                  timeframe === tf
                    ? 'bg-slate-800 text-slate-100'
                    : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                {tf.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 3. Canvas Container */}
      <div ref={containerRef} className="relative flex-1 w-full min-w-0 min-h-0 bg-[#090d14] overflow-hidden">
        {isLoading && !marketData && (
          <div className="absolute inset-0 z-10 flex flex-col justify-between bg-[#090d14] p-6">
            <div className="flex items-center justify-between font-mono text-[10px] text-slate-500 tracking-wider">
              <span>SYNCHRONIZING REAL-TIME KLINES...</span>
              <span className="flex items-center gap-1.5">
                <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse" />
                BINANCE WS
              </span>
            </div>
            <div className="w-full flex-1 flex flex-col justify-around py-4 opacity-15">
              <div className="w-full border-b border-dashed border-slate-700" />
              <div className="w-full border-b border-dashed border-slate-700" />
              <div className="w-full border-b border-dashed border-slate-700" />
              <div className="w-full border-b border-dashed border-slate-700" />
            </div>
            <div className="flex items-center justify-between font-mono text-[10px] text-slate-600">
              <span>1H CANDLE DISCIPLINE</span>
              <span>100 INTERVALS BUFFERED</span>
            </div>
          </div>
        )}
        <div ref={chartContainerRef} className="absolute inset-0 w-full h-full" />
      </div>
    </div>
  )
}
