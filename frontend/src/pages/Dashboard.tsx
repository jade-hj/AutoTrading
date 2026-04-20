import { useState, useCallback } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { dashboardApi, logsApi, DashboardSummary, KospiData } from '../api/client'
import { usePolling } from '../hooks/usePolling'
import StatCard from '../components/StatCard'

function fmt(n: number) { return n.toLocaleString('ko-KR') }
function fmtPnl(n: number) {
  const sign = n >= 0 ? '+' : ''
  return `${sign}${fmt(Math.round(n))}원`
}

export default function Dashboard() {
  const [summary, setSummary]   = useState<DashboardSummary | null>(null)
  const [kospi,   setKospi]     = useState<KospiData | null>(null)
  const [pnlData, setPnlData]   = useState<{ date: string; pnl: number }[]>([])
  const [loading, setLoading]   = useState(true)

  const fetchAll = useCallback(async () => {
    try {
      const [s, k, p] = await Promise.all([
        dashboardApi.summary(),
        dashboardApi.kospi(),
        logsApi.dailyPnl(14),
      ])
      setSummary(s.data)
      setKospi(k.data)
      setPnlData(p.data.daily_pnl)
    } catch { /* ignore */ } finally {
      setLoading(false)
    }
  }, [])

  usePolling(fetchAll, 10_000)

  const pnl = summary?.daily_pnl ?? 0

  return (
    <div className="p-5 space-y-5 overflow-y-auto h-full">
      <h2 className="text-sm font-semibold text-white">대시보드</h2>

      {/* 상단 지표 카드 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          label="예수금"
          value={summary ? `${fmt(summary.available_cash)}원` : '-'}
          loading={loading}
        />
        <StatCard
          label="총평가"
          value={summary ? `${fmt(summary.total_eval)}원` : '-'}
          loading={loading}
        />
        <StatCard
          label="당일 실현 손익"
          value={summary ? fmtPnl(pnl) : '-'}
          color={pnl > 0 ? 'green' : pnl < 0 ? 'red' : 'default'}
          loading={loading}
        />
        <StatCard
          label="보유 종목"
          value={summary ? `${summary.holdings_count}종목` : '-'}
          sub={summary?.daily_loss_limit_reached ? '⚠ 일일 손실 한도 도달' : undefined}
          loading={loading}
        />
      </div>

      {/* KOSPI */}
      <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-4">
        <p className="text-[#8b949e] text-xs mb-2">KOSPI</p>
        {loading ? (
          <div className="h-8 bg-[#21262d] rounded animate-pulse w-48" />
        ) : kospi ? (
          <div className="flex items-baseline gap-3">
            <span className="text-2xl font-bold text-white">
              {kospi.index.toFixed(2)}
            </span>
            <span className={`text-sm font-medium ${kospi.change_rate >= 0 ? 'text-[#3fb950]' : 'text-[#f85149]'}`}>
              {kospi.change_rate >= 0 ? '▲' : '▼'} {Math.abs(kospi.change).toFixed(2)} ({kospi.change_rate >= 0 ? '+' : ''}{kospi.change_rate.toFixed(2)}%)
            </span>
            <span className="text-[#8b949e] text-xs">거래량 {fmt(kospi.volume)}</span>
          </div>
        ) : (
          <span className="text-[#8b949e]">조회 실패</span>
        )}
      </div>

      {/* 14일 일별 손익 차트 */}
      <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-4">
        <p className="text-[#8b949e] text-xs mb-4">14일 일별 실현 손익</p>
        <ResponsiveContainer width="100%" height={160}>
          <BarChart data={pnlData} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
            <XAxis dataKey="date" tick={{ fill: '#8b949e', fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: '#8b949e', fontSize: 10 }} axisLine={false} tickLine={false} width={60}
              tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`} />
            <Tooltip
              contentStyle={{ background: '#21262d', border: '1px solid #30363d', borderRadius: 6, fontSize: 12 }}
              formatter={(v) => [fmtPnl(Number(v ?? 0)), '손익']}
              labelStyle={{ color: '#8b949e' }}
            />
            <Bar dataKey="pnl" radius={[3, 3, 0, 0]}>
              {pnlData.map((entry, i) => (
                <Cell key={i} fill={entry.pnl >= 0 ? '#3fb950' : '#f85149'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
