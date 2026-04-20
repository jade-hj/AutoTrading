import { useState, useCallback } from 'react'
import { scanApi, Candidate } from '../api/client'
import { usePolling } from '../hooks/usePolling'

function fmt(n: number) { return n.toLocaleString('ko-KR') }

export default function Scan() {
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [scannedAt, setScannedAt]   = useState<string | null>(null)
  const [running, setRunning]       = useState(false)
  const [analyzing, setAnalyzing]   = useState<string | null>(null)
  const [analysisResult, setResult] = useState<Record<string, unknown> | null>(null)

  const fetchCandidates = useCallback(async () => {
    try {
      const res = await scanApi.candidates()
      setCandidates(res.data.candidates)
      setScannedAt(res.data.scanned_at)
    } catch { /* ignore */ }
  }, [])

  usePolling(fetchCandidates, 30_000)

  const handleScan = async () => {
    setRunning(true)
    try {
      const res = await scanApi.run()
      setCandidates(res.data.candidates)
      setScannedAt(new Date().toLocaleTimeString('ko-KR'))
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '스캔 실패'
      alert(msg)
    } finally {
      setRunning(false)
    }
  }

  const handleAnalyze = async (code: string) => {
    setAnalyzing(code)
    setResult(null)
    try {
      const res = await scanApi.analyze(code)
      setResult(res.data as Record<string, unknown>)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '분석 실패'
      alert(msg)
    } finally {
      setAnalyzing(null)
    }
  }

  return (
    <div className="p-5 space-y-4 overflow-y-auto h-full">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">
          종목 스캔
          {scannedAt && <span className="text-[#8b949e] font-normal ml-2 text-xs">마지막 스캔: {scannedAt}</span>}
        </h2>
        <button onClick={handleScan} disabled={running}
          className="text-xs px-4 py-1.5 rounded bg-[#58a6ff]/20 text-[#58a6ff] border border-[#58a6ff]/40
                     hover:bg-[#58a6ff]/30 disabled:opacity-50 transition-colors">
          {running ? '스캔 중...' : '즉시 스캔'}
        </button>
      </div>

      {/* 후보 테이블 */}
      <div className="bg-[#161b22] border border-[#30363d] rounded-lg overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-[#30363d]">
              {['종목', '현재가', '등락률', '거래량', 'RSI', 'MA정배열', 'AI 분석'].map(h => (
                <th key={h} className="px-3 py-2.5 text-left text-[#8b949e] font-normal">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {candidates.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-[#8b949e]">
                  스캔 결과가 없습니다. 스캔을 실행해주세요.
                </td>
              </tr>
            ) : candidates.map((c) => {
              const ind  = c.indicators as Record<string, unknown>
              const rsi  = ind?.rsi as number | undefined
              const ma   = ind?.ma as Record<string, unknown> | undefined
              const rate = c.change_rate

              return (
                <tr key={c.stock_code} className="border-b border-[#21262d] hover:bg-[#21262d] transition-colors">
                  <td className="px-3 py-2.5">
                    <p className="text-white font-medium">{c.stock_name}</p>
                    <p className="text-[#8b949e]">{c.stock_code}</p>
                  </td>
                  <td className="px-3 py-2.5 text-white">{fmt(c.current_price)}원</td>
                  <td className={`px-3 py-2.5 font-medium ${rate >= 0 ? 'text-[#3fb950]' : 'text-[#f85149]'}`}>
                    {rate >= 0 ? '+' : ''}{rate.toFixed(2)}%
                  </td>
                  <td className="px-3 py-2.5 text-[#8b949e]">{fmt(c.volume)}</td>
                  <td className="px-3 py-2.5">
                    {rsi !== undefined ? (
                      <span className={`font-medium ${rsi >= 50 && rsi <= 70 ? 'text-[#3fb950]' : rsi > 70 ? 'text-[#f85149]' : 'text-[#8b949e]'}`}>
                        {rsi.toFixed(1)}
                      </span>
                    ) : '-'}
                  </td>
                  <td className="px-3 py-2.5">
                    {ma?.uptrend ? (
                      <span className="text-[#3fb950]">정배열</span>
                    ) : (
                      <span className="text-[#8b949e]">-</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5">
                    <button onClick={() => handleAnalyze(c.stock_code)}
                      disabled={analyzing === c.stock_code}
                      className="text-xs px-2 py-1 rounded border border-[#58a6ff]/40 text-[#58a6ff]
                                 hover:bg-[#58a6ff]/10 disabled:opacity-50 transition-colors">
                      {analyzing === c.stock_code ? '분석 중...' : '분석'}
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* 분석 결과 패널 */}
      {analysisResult && (
        <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white">
              [{analysisResult.stock_code as string}] {analysisResult.stock_name as string} 분석 결과
            </h3>
            <span className={`text-xs font-bold px-2 py-0.5 rounded ${
              analysisResult.action === 'BUY'  ? 'bg-[#3fb950]/20 text-[#3fb950]' :
              analysisResult.action === 'SELL' ? 'bg-[#f85149]/20 text-[#f85149]' :
                                                  'bg-[#21262d] text-[#8b949e]'}`}>
              {analysisResult.action as string}
            </span>
          </div>

          <div className="grid grid-cols-3 gap-3 text-xs">
            {['market', 'signal', 'risk'].map((key) => {
              const d = analysisResult[key] as Record<string, unknown> | null
              if (!d) return null
              const labels: Record<string, string> = { market: '시장 필터', signal: '신호', risk: '리스크' }
              return (
                <div key={key} className="bg-[#21262d] rounded p-3 space-y-1.5">
                  <p className="text-[#8b949e] font-medium">{labels[key]}</p>
                  <p className={`font-bold ${
                    (d.go === true || d.action === 'BUY' || d.approved === true)
                      ? 'text-[#3fb950]' : 'text-[#f85149]'}`}>
                    {d.go !== undefined ? (d.go ? 'GO' : 'NO-GO') :
                     d.action !== undefined ? d.action as string :
                     d.approved ? 'OK' : 'REJECT'}
                  </p>
                  {d.confidence !== undefined && (
                    <p className="text-[#8b949e]">확신도 {((d.confidence as number) * 100).toFixed(0)}%</p>
                  )}
                  <p className="text-[#c9d1d9] leading-relaxed">{d.reasoning as string}</p>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
