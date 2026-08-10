import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowRightIcon, CheckIcon } from '../../components/icons'
import { cn } from '../../lib/cn'

export type SlideToStartProps = {
  /** 끝까지 밀었을 때 1회 호출 */
  onComplete: () => void
  label?: string
}

/** 끝까지 밀었다고 볼 비율 */
const DONE_AT = 0.92
/** 키보드 화살표 한 번에 움직이는 양 */
const KEY_STEP = 0.25

/**
 * 밀어서 시작하는 버튼.
 * 손잡이를 오른쪽 끝까지 끌면 완료 — 그 전까지는 반투명 흰색, 완료되면 액센트로 채워진다.
 * 드래그만으로는 키보드·보조기기에서 쓸 수 없어 slider 역할을 주고
 * 화살표/Home·End/Enter로도 같은 동작을 할 수 있게 했다.
 */
export function SlideToStart({ onComplete, label = '밀어서 순찰 시작' }: SlideToStartProps) {
  const trackRef = useRef<HTMLDivElement>(null)
  const [progress, setProgress] = useState(0)
  const [done, setDone] = useState(false)
  const [dragging, setDragging] = useState(false)
  const doneRef = useRef(false)

  /** 손잡이가 움직일 수 있는 최대 거리(px) */
  const travel = useCallback(() => {
    const el = trackRef.current
    if (!el) return 1
    // 트랙 안쪽 여백(6px)과 손잡이 지름을 뺀 나머지가 실제 이동 구간
    const thumb = el.querySelector<HTMLElement>('.slide-start__thumb')
    return Math.max(1, el.clientWidth - (thumb?.offsetWidth ?? 56) - 12)
  }, [])

  const timerRef = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timerRef.current), [])

  const finish = useCallback(() => {
    if (doneRef.current) return
    doneRef.current = true
    setDone(true)
    setProgress(1)
    // 액센트로 꽉 찬 완료 상태를 잠깐 보여준 뒤 다음 단계로 넘긴다
    // (바로 넘기면 애써 만든 색 전환이 보이지 않는다)
    timerRef.current = window.setTimeout(onComplete, 620)
  }, [onComplete])

  const moveTo = useCallback(
    (clientX: number) => {
      const el = trackRef.current
      if (!el) return
      const rect = el.getBoundingClientRect()
      const x = clientX - rect.left - 6 - (el.querySelector<HTMLElement>('.slide-start__thumb')?.offsetWidth ?? 56) / 2
      setProgress(Math.min(1, Math.max(0, x / travel())))
    },
    [travel],
  )

  // 드래그 중에는 트랙 밖으로 나가도 따라오도록 window에서 듣는다
  useEffect(() => {
    if (!dragging) return
    const onMove = (e: PointerEvent) => moveTo(e.clientX)
    const onUp = (e: PointerEvent) => {
      setDragging(false)
      const el = trackRef.current
      if (!el) return
      const rect = el.getBoundingClientRect()
      const thumbW = el.querySelector<HTMLElement>('.slide-start__thumb')?.offsetWidth ?? 56
      const p = Math.min(1, Math.max(0, (e.clientX - rect.left - 6 - thumbW / 2) / travel()))
      if (p >= DONE_AT) finish()
      else setProgress(0) // 못 미치면 제자리로
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    window.addEventListener('pointercancel', onUp)
    return () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      window.removeEventListener('pointercancel', onUp)
    }
  }, [dragging, moveTo, travel, finish])

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (done) return
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'End') {
      e.preventDefault()
      finish()
    } else if (e.key === 'ArrowRight' || e.key === 'ArrowUp') {
      e.preventDefault()
      const next = Math.min(1, progress + KEY_STEP)
      setProgress(next)
      if (next >= DONE_AT) finish()
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') {
      e.preventDefault()
      setProgress(Math.max(0, progress - KEY_STEP))
    } else if (e.key === 'Home') {
      e.preventDefault()
      setProgress(0)
    }
  }

  return (
    <div
      ref={trackRef}
      className={cn('slide-start', done && 'is-done', dragging && 'is-dragging')}
      style={{ '--p': progress } as React.CSSProperties}
      role="slider"
      tabIndex={done ? -1 : 0}
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(progress * 100)}
      aria-valuetext={done ? '순찰 시작됨' : `${Math.round(progress * 100)}% — 끝까지 밀면 시작`}
      onKeyDown={onKeyDown}
      onPointerDown={(e) => {
        if (done) return
        setDragging(true)
        moveTo(e.clientX)
      }}
    >
      {/* 진행한 만큼 액센트가 차오른다 */}
      <span className="slide-start__fill" aria-hidden />
      <span className="slide-start__label" aria-hidden>
        {done ? '순찰 시작' : label}
      </span>
      <span className="slide-start__thumb" aria-hidden>
        {done ? <CheckIcon /> : <ArrowRightIcon />}
      </span>
    </div>
  )
}
