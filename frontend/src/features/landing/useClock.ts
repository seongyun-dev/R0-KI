import { useEffect, useState } from 'react'

const pad2 = (n: number) => String(n).padStart(2, '0')

function now() {
  const d = new Date()
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`
}

/** 관제 시각 라이브 시계 — "HH:MM:SS" */
export function useClock() {
  const [time, setTime] = useState(now)
  useEffect(() => {
    const t = setInterval(() => setTime(now()), 1000)
    return () => clearInterval(t)
  }, [])
  return time
}
