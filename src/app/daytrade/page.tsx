'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { RefreshCw, TrendingUp, TrendingDown, Minus, AlertTriangle, Zap } from 'lucide-react'
import { daytradeService, DayTradeCandidate, DayTradeSignal } from '@/services/daytradeService'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

const STATUS_CONFIG = {
  bullish: {
    label: '看漲',
    icon: TrendingUp,
    className: 'text-red-500 bg-red-50 border-red-200',
    badge: 'bg-red-100 text-red-700 border-red-200',
  },
  bearish: {
    label: '看跌',
    icon: TrendingDown,
    className: 'text-green-600 bg-green-50 border-green-200',
    badge: 'bg-green-100 text-green-700 border-green-200',
  },
  warning: {
    label: '警示',
    icon: AlertTriangle,
    className: 'text-yellow-600 bg-yellow-50 border-yellow-200',
    badge: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  },
  neutral: {
    label: '中性',
    icon: Minus,
    className: 'text-muted-foreground bg-muted/30',
    badge: 'bg-muted text-muted-foreground',
  },
}

function SignalBadge({ signal }: { signal: DayTradeSignal }) {
  const cfg = STATUS_CONFIG[signal.status]
  const Icon = cfg.icon
  return (
    <div
      className={cn('flex items-start gap-1.5 rounded-md border px-2 py-1.5 text-xs', cfg.className)}
      title={signal.description}
    >
      <Icon className="mt-0.5 h-3 w-3 shrink-0" />
      <span className="leading-tight">{signal.description}</span>
    </div>
  )
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.min(Math.abs(score), 100)
  const positive = score > 0
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-24 overflow-hidden rounded-full bg-muted">
        <div
          className={cn('h-full rounded-full transition-all', positive ? 'bg-red-500' : 'bg-green-600')}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={cn('text-xs font-bold tabular-nums', positive ? 'text-red-500' : score < 0 ? 'text-green-600' : 'text-muted-foreground')}>
        {score > 0 ? '+' : ''}{score}
      </span>
    </div>
  )
}

function CandidateRow({ c }: { c: DayTradeCandidate }) {
  const priceUp = c.change_percent > 0
  const priceDown = c.change_percent < 0

  return (
    <div className="border-b last:border-0 p-4 hover:bg-muted/20 transition-colors">
      {/* Stock header */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-semibold">{c.stock_id}</span>
          <span className="text-sm text-muted-foreground">{c.stock_name}</span>
          {c.is_intraday && (
            <Badge variant="outline" className="border-blue-300 bg-blue-50 text-blue-600 text-xs">
              盤中即時
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <div className="font-bold tabular-nums">{c.current_price.toFixed(2)}</div>
            <div className={cn('text-xs tabular-nums', priceUp ? 'text-red-500' : priceDown ? 'text-green-600' : 'text-muted-foreground')}>
              {c.change_percent > 0 ? '+' : ''}{c.change_percent.toFixed(2)}%
            </div>
          </div>
          <ScoreBar score={c.score} />
        </div>
      </div>

      {/* Signal grid */}
      <div className="grid gap-2 sm:grid-cols-3">
        <SignalBadge signal={c.signals.ma_squeeze} />
        <SignalBadge signal={c.signals.institutional} />
        <SignalBadge signal={c.signals.price_volume} />
      </div>
    </div>
  )
}

export default function DaytradePage() {
  const [filter, setFilter] = useState<'all' | 'bullish' | 'bearish'>('all')

  const { data, isLoading, refetch, dataUpdatedAt } = useQuery({
    queryKey: ['daytrade-scan'],
    queryFn: () => daytradeService.scan(),
    staleTime: 30000,
    refetchInterval: 60000,
  })

  const candidates = data ?? []
  const filtered = candidates.filter((c) => {
    if (filter === 'bullish') return c.score > 0
    if (filter === 'bearish') return c.score < 0
    return true
  })

  const bullishCount = candidates.filter((c) => c.score > 0).length
  const bearishCount = candidates.filter((c) => c.score < 0).length

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Zap className="h-5 w-5 text-yellow-500" />
          <h1 className="text-xl font-bold">當沖監測</h1>
        </div>
        <div className="flex items-center gap-2">
          {dataUpdatedAt > 0 && (
            <span className="text-xs text-muted-foreground">
              更新：{new Date(dataUpdatedAt).toLocaleTimeString('zh-TW')}
            </span>
          )}
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={cn('h-4 w-4', isLoading && 'animate-spin')} />
          </Button>
        </div>
      </div>

      {/* Signal legend */}
      <div className="flex flex-wrap gap-2 text-xs">
        {Object.entries(STATUS_CONFIG).map(([status, cfg]) => {
          const Icon = cfg.icon
          return (
            <span key={status} className={cn('flex items-center gap-1 rounded border px-2 py-0.5', cfg.badge)}>
              <Icon className="h-3 w-3" />
              {cfg.label}
            </span>
          )
        })}
        <span className="text-muted-foreground ml-1">• 分數越高代表多方信號越強</span>
      </div>

      {/* Stats + filter */}
      <div className="flex items-center gap-2">
        <Button variant={filter === 'all' ? 'default' : 'outline'} size="sm" onClick={() => setFilter('all')}>
          全部 {candidates.length}
        </Button>
        <Button variant={filter === 'bullish' ? 'default' : 'outline'} size="sm" onClick={() => setFilter('bullish')}
          className={filter === 'bullish' ? '' : 'text-red-500 border-red-200'}>
          多方 {bullishCount}
        </Button>
        <Button variant={filter === 'bearish' ? 'default' : 'outline'} size="sm" onClick={() => setFilter('bearish')}
          className={filter === 'bearish' ? '' : 'text-green-600 border-green-200'}>
          空方 {bearishCount}
        </Button>
      </div>

      {/* Candidate list */}
      <Card>
        <CardHeader className="pb-0">
          <CardTitle className="text-sm text-muted-foreground font-normal">
            依信號強度排序，共 {filtered.length} 檔
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-16 text-muted-foreground">
              <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
              掃描中...
            </div>
          ) : filtered.length === 0 ? (
            <div className="py-16 text-center text-sm text-muted-foreground">
              目前無符合條件的標的
            </div>
          ) : (
            filtered.map((c) => <CandidateRow key={c.stock_id} c={c} />)
          )}
        </CardContent>
      </Card>

      {/* Disclaimer */}
      <p className="text-xs text-muted-foreground text-center">
        僅供研究參考，不構成投資建議。當沖交易風險極高，請謹慎評估。
      </p>
    </div>
  )
}
