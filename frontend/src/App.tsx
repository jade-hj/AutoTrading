import { useState, useCallback } from 'react'
import Header from './components/Header'
import Sidebar, { Page } from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import Positions from './pages/Positions'
import Scan from './pages/Scan'
import Chart from './pages/Chart'
import Logs from './pages/Logs'
import Settings from './pages/Settings'
import { systemApi, SystemStatus } from './api/client'
import { usePolling } from './hooks/usePolling'
import './index.css'

export default function App() {
  const [page,   setPage]   = useState<Page>('dashboard')
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [ctrlLoading, setCtrlLoading] = useState(false)

  const fetchStatus = useCallback(async () => {
    try {
      const res = await systemApi.status()
      setStatus(res.data)
    } catch { /* 서버 미연결 시 무시 */ }
  }, [])

  usePolling(fetchStatus, 5_000)

  const handleStart = async () => {
    setCtrlLoading(true)
    try {
      await systemApi.start()
      await fetchStatus()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '시작 실패'
      alert(msg)
    } finally {
      setCtrlLoading(false)
    }
  }

  const handleStop = async () => {
    if (!confirm('봇을 중지하시겠습니까?')) return
    setCtrlLoading(true)
    try {
      await systemApi.stop()
      await fetchStatus()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '중지 실패'
      alert(msg)
    } finally {
      setCtrlLoading(false)
    }
  }

  const pageMap: Record<Page, JSX.Element> = {
    dashboard: <Dashboard />,
    positions: <Positions />,
    scan:      <Scan />,
    chart:     <Chart />,
    logs:      <Logs />,
    settings:  <Settings />,
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <Header
        status={status}
        onStart={handleStart}
        onStop={handleStop}
        loading={ctrlLoading}
      />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar current={page} onChange={setPage} />
        <main className="flex-1 overflow-hidden">
          {pageMap[page]}
        </main>
      </div>
    </div>
  )
}
