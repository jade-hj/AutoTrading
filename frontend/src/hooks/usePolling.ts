import { useEffect, useRef } from 'react'

/** interval ms 마다 fn 을 반복 호출. 즉시 1회 실행 후 폴링. */
export function usePolling(fn: () => void, interval: number, enabled = true) {
  const fnRef = useRef(fn)
  fnRef.current = fn

  useEffect(() => {
    if (!enabled) return
    fnRef.current()
    const id = setInterval(() => fnRef.current(), interval)
    return () => clearInterval(id)
  }, [interval, enabled])
}
