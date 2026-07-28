import { useEffect, useState } from 'react'

/** 경과 시간 실시간 카운트 — "3분 12초" 형식 (긴급 알림 1c+/1o/1h 공용) */
export function useElapsed(active: boolean, startSec = 0) {
  const [sec, setSec] = useState(startSec)
  // startSec가 뒤늦게 확정되면(비동기 로딩 등) 기준값으로 리셋. 상수로 넘기면 변화 없음.
  useEffect(() => {
    setSec(startSec)
  }, [startSec])
  useEffect(() => {
    if (!active) return
    const t = setInterval(() => setSec((s) => s + 1), 1000)
    return () => clearInterval(t)
  }, [active])
  return `${Math.floor(sec / 60)}분 ${String(sec % 60).padStart(2, '0')}초`
}
