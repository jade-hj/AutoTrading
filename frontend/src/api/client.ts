import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 10000 })

// ── Types ──────────────────────────────────────────────────

export interface SystemStatus {
  is_running:       boolean
  mode:             string
  session:          string
  uptime_sec:       number | null
  start_time:       string | null
  position_count:   number
  daily_pnl:        number
  last_scan_time:   string | null
}

export interface DashboardSummary {
  available_cash:           number
  total_eval:               number
  holdings_count:           number
  daily_pnl:                number
  daily_loss_limit_reached: boolean
}

export interface KospiData {
  index:       number
  change:      number
  change_rate: number
  volume:      number
}

export interface Position {
  stock_code:   string
  stock_name:   string
  quantity:     number
  entry_price:  number
  current_price: number
  stop_loss:    number
  tp1:          number
  tp2:          number
  tp1_hit:      boolean
  pnl:          number
  pnl_rate:     number
}

export interface Candidate {
  stock_code:   string
  stock_name:   string
  current_price: number
  change_rate:  number
  volume:       number
  market:       string
  indicators:   Record<string, unknown>
}

export interface Trade {
  timestamp:  string
  action:     'BUY' | 'SELL'
  stock_code: string
  stock_name: string
  price:      number
  quantity:   number
  pnl:        number
  pnl_rate:   number
  order_no:   string
  reason:     string
}

export interface LogEntry {
  ts:      string
  level:   string
  name:    string
  message: string
}

export interface Candle {
  date:   string
  open:   number
  high:   number
  low:    number
  close:  number
  volume: number
}

export interface SystemSettings {
  scan:   Record<string, unknown>
  common: Record<string, unknown>
  am:     Record<string, unknown>
  pm:     Record<string, unknown>
}

// ── API calls ───────────────────────────────────────────────

export const systemApi = {
  status:       () => api.get<SystemStatus>('/system/status'),
  start:        () => api.post('/system/start'),
  stop:         () => api.post('/system/stop'),
  getSettings:  () => api.get<SystemSettings>('/system/settings'),
  patchSetting: (key: string, value: unknown) =>
    api.patch('/system/settings', { key, value }),
}

export const dashboardApi = {
  summary: () => api.get<DashboardSummary>('/dashboard/summary'),
  kospi:   () => api.get<KospiData>('/dashboard/kospi'),
}

export const positionsApi = {
  list:  () => api.get<Position[]>('/positions'),
  close: (code: string) => api.delete(`/positions/${code}`),
}

export const scanApi = {
  candidates: () => api.get<{ candidates: Candidate[]; scanned_at: string | null; count: number }>('/scan/candidates'),
  run:        () => api.post<{ candidates: Candidate[]; count: number }>('/scan/run'),
  analyze:    (code: string) => api.get(`/scan/analyze/${code}`),
}

export const chartApi = {
  candles:    (code: string, count = 40) => api.get<{ candles: Candle[] }>(`/chart/${code}/candles?count=${count}`),
  daily:      (code: string, count = 60) => api.get<{ candles: Candle[] }>(`/chart/${code}/daily?count=${count}`),
  indicators: (code: string) => api.get(`/chart/${code}/indicators`),
  price:      (code: string) => api.get(`/chart/${code}/price`),
}

export const logsApi = {
  trades:   () => api.get<{ trades: Trade[]; count: number }>('/logs/trades'),
  system:   (tail = 100) => api.get<{ logs: LogEntry[] }>(`/logs/system?tail=${tail}`),
  dailyPnl: (days = 30) => api.get<{ daily_pnl: { date: string; pnl: number }[] }>(`/logs/daily-pnl?days=${days}`),
}

export const ordersApi = {
  buy:  (stock_code: string, quantity: number, price = 0) =>
    api.post('/orders/buy', { stock_code, quantity, price }),
  sell: (stock_code: string, quantity: number, price = 0) =>
    api.post('/orders/sell', { stock_code, quantity, price }),
}
