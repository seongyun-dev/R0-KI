import { useEffect, useRef, useState } from 'react'
import { BrandMark } from '../../components/icons'

const FILL_MS = 1300
const easeInOutCubic = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)
const pad3 = (n: number) => String(n).padStart(3, '0')

/** 부팅 로더 — 카운트업 후 위로 슬라이드 아웃, 완료 시 onDone (프로토타입 포팅) */
export function Loader({ onDone }: { onDone: () => void }) {
  const [progress, setProgress] = useState(0)
  const [exit, setExit] = useState(false)
  const doneRef = useRef(false)

  useEffect(() => {
    const start = performance.now()
    let raf = 0
    const tick = (now: number) => {
      const t = Math.min((now - start) / FILL_MS, 1)
      setProgress(Math.round(easeInOutCubic(t) * 100))
      if (t < 1) raf = requestAnimationFrame(tick)
      else setExit(true)
    }
    raf = requestAnimationFrame(tick)
    // rAF가 멈춘 환경(백그라운드 탭 등)에서 로더에 갇히지 않도록 하는 안전장치
    const guard = setTimeout(() => {
      setProgress(100)
      setExit(true)
    }, FILL_MS + 1200)
    return () => {
      cancelAnimationFrame(raf)
      clearTimeout(guard)
    }
  }, [])

  // exit 트랜지션(0.7s) 종료 후 onDone — transitionend 유실 대비 타임아웃 폴백
  useEffect(() => {
    if (!exit) return
    const finish = () => {
      if (doneRef.current) return
      doneRef.current = true
      onDone()
    }
    const t = setTimeout(finish, 900)
    return () => clearTimeout(t)
  }, [exit, onDone])

  return (
    <div className={`loader${exit ? ' exit' : ''}`} aria-hidden={exit}>
      <div className="loader__center">
        <div className="loader__brand">
          <BrandMark className="mk" />
          <span>AI 순찰 시스템</span>
        </div>
        <p className="loader__tag">단지의 눈이 되는 자율 순찰 로봇 — 관제 시스템을 준비하고 있습니다.</p>
      </div>
      <div className="loader__progress">
        <div className="loader__track">
          <div className="loader__fill" style={{ width: `${progress}%` }} />
        </div>
        <div className="loader__row">
          <span>SYSTEM BOOT</span>
          <span className="loader__count font-mono tabular">{pad3(progress)}</span>
        </div>
      </div>
    </div>
  )
}
