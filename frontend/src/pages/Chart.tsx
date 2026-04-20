import { useState } from 'react'
import {
  ComposedChart, Bar, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from 'recharts'
import { chartApi, Candle } from '../api/client'

function fmt(n: number) { return n.toLocaleString('ko-KR') }

export default function Chart() {
  const [code, setCode]         = useState('')
  const [input, setInput]       = useState('')
  const [candles, setCandles]   = useState<Candle[]>([])
  const [mode, setMode]         = useState<'minute' | 'daily'>('minute')
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState('')

  const handleSearch = async () => {
    const trimmed = input.trim()
    if (!trimmed) return
    setLoading(true)
    setError('')
    try {
      const res = mode === 'minute'
        ? await chartApi.candles(trimmed, 40)
        : await chartApi.daily(trimmed, 60)
      setCandles(res.data.candles)
      setCode(trimmed)
    } catch {
      setError('조회 실패. 종목코드를 확인해주세요.')
    } finally {
      setLoading(false)
    }
  }

  // Recharts 용 데이터 가공 (OHLC + 거래량)
  const chartData = candles.map((c) => ({
    date:   c.date.slice(0, 5),   // HHMM or MMDD
    open:   c.open,
    high:   c.high,
    low:    c.low,
    close:  c.close,
    volume: c.volume,
    // 음양봉 색상 계산용
    change: c.close - c.open,
    // 캔들 범위 (Recharts Bar로 표현)
    bodyLow:  Math.min(c.open, c.close),
    bodyHigh: Math.max(c.open, c.close),
  }))

  return (
    <div className="p-5 space-y-4 overflow-y-auto h-full">
      <h2 className="text-sm font-semibold text-white">차트</h2>

      {/* 검색 바 */}
      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          placeholder="종목코드 입력 (예: 005930)"
          className="flex-1 bg-[#21262d] border border-[#30363d] rounded px-3 py-2 text-xs text-white
                     placeholder-[#8b949e] focus:outline-none focus:border-[#58a6ff]"
        />
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value as 'minute' | 'daily')}
          className="bg-[#21262d] border border-[#30363d] rounded px-2 py-2 text-xs text-white focus:outline-none"
        >
          <option value="minute">분봉</option>
          <option value="daily">일봉</option>
        </select>
        <button onClick={handleSearch} disabled={loading}
          className="text-xs px-4 py-2 rounded bg-[#58a6ff]/20 text-[#58a6ff] border border-[#58a6ff]/40
                     hover:bg-[#58a6ff]/30 disabled:opacity-50 transition-colors">
          {loading ? '조회 중...' : '조회'}
        </button>
      </div>

      {error && <p className="text-[#f85149] text-xs">{error}</p>}

      {candles.length > 0 && (
        <>
          <p className="text-[#8b949e] text-xs">{code} · {mode === 'minute' ? '분봉' : '일봉'} {candles.length}개</p>

          {/* 가격 차트 */}
          <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-4">
            <ResponsiveContainer width="100%" height={240}>
              <ComposedChart data={chartData} margin={{ top: 5, right: 5, left: 5, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
                <XAxis dataKey="date" tick={{ fill: '#8b949e', fontSize: 10 }} axisLine={false} tickLine={false}
                  interval={Math.floor(chartData.length / 8)} />
                <YAxis domain={['auto', 'auto']} tick={{ fill: '#8b949e', fontSize: 10 }}
                  axisLine={false} tickLine={false} width={65}
                  tickFormatter={(v) => fmt(v)} />
                <Tooltip
                  contentStyle={{ background: '#21262d', border: '1px solid #30363d', borderRadius: 6, fontSize: 11 }}
                  labelStyle={{ color: '#8b949e' }}
                  formatter={(v, name) => [fmt(Number(v ?? 0)), String(name)]}
                />
                {/* 종가 라인 */}
                <Line type="monotone" dataKey="close" dot={false} stroke="#58a6ff" strokeWidth={1.5} />
                {/* 고가 */}
                <Line type="monotone" dataKey="high" dot={false} stroke="#3fb950" strokeWidth={0.8} strokeDasharray="2 2" />
                {/* 저가 */}
                <Line type="monotone" dataKey="low" dot={false} stroke="#f85149" strokeWidth={0.8} strokeDasharray="2 2" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* 거래량 차트 */}
          <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-4">
            <p className="text-[#8b949e] text-xs mb-3">거래량</p>
            <ResponsiveContainer width="100%" height={80}>
              <ComposedChart data={chartData} margin={{ top: 0, right: 5, left: 5, bottom: 0 }}>
                <XAxis hide />
                <YAxis tick={{ fill: '#8b949e', fontSize: 10 }} axisLine={false} tickLine={false} width={65}
                  tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`} />
                <Bar dataKey="volume" fill="#30363d" radius={[2, 2, 0, 0]} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* 최근 5개 봉 요약 */}
          <div className="bg-[#161b22] border border-[#30363d] rounded-lg overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[#30363d]">
                  {['시간/날짜','시가','고가','저가','종가','거래량','등락'].map(h => (
                    <th key={h} className="px-3 py-2 text-left text-[#8b949e] font-normal">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[...candles].reverse().slice(0, 10).map((c, i) => {
                  const chg = ((c.close - c.open) / c.open * 100)
                  return (
                    <tr key={i} className="border-b border-[#21262d]">
                      <td className="px-3 py-1.5 text-[#8b949e]">{c.date}</td>
                      <td className="px-3 py-1.5 text-white">{fmt(c.open)}</td>
                      <td className="px-3 py-1.5 text-[#3fb950]">{fmt(c.high)}</td>
                      <td className="px-3 py-1.5 text-[#f85149]">{fmt(c.low)}</td>
                      <td className="px-3 py-1.5 text-white font-medium">{fmt(c.close)}</td>
                      <td className="px-3 py-1.5 text-[#8b949e]">{fmt(c.volume)}</td>
                      <td className={`px-3 py-1.5 font-medium ${chg >= 0 ? 'text-[#3fb950]' : 'text-[#f85149]'}`}>
                        {chg >= 0 ? '+' : ''}{chg.toFixed(2)}%
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
