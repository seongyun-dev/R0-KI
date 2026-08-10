import { useEffect, useState } from 'react'

export function formatElapsed(totalSeconds: number) {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds))
  const days = Math.floor(safeSeconds / 86_400)
  const hours = Math.floor((safeSeconds % 86_400) / 3_600)
  const minutes = Math.floor((safeSeconds % 3_600) / 60)
  const seconds = safeSeconds % 60

  if (days > 0) return `${days}일 ${hours}시간 ${minutes}분`
  if (hours > 0) return `${hours}시간 ${minutes}분`
  return `${minutes}분 ${String(seconds).padStart(2, '0')}초`
}

/** 경과 시간 실시간 카운트 — 길이에 따라 분·초 / 시간·분 / 일·시간·분으로 표시 */
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
  return formatElapsed(sec)
}
