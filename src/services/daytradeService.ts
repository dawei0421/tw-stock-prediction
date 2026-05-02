import { api } from '@/services/api'

export interface DayTradeSignal {
  status: 'bullish' | 'bearish' | 'warning' | 'neutral'
  value: number
  description: string
}

export interface DayTradeCandidate {
  stock_id: string
  stock_name: string
  current_price: number
  change_percent: number
  score: number
  is_intraday: boolean
  signals: {
    ma_squeeze: DayTradeSignal
    institutional: DayTradeSignal
    price_volume: DayTradeSignal
  }
}

export interface DaytradeScanResult {
  data: DayTradeCandidate[]
  count: number
  timestamp: string
}

export const daytradeService = {
  async scan(stocks?: string): Promise<DayTradeCandidate[]> {
    const params = stocks ? { stocks } : undefined
    return api.get<DayTradeCandidate[]>('/daytrade/scan', params)
  },
}
