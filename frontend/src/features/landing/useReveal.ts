import { useEffect, useRef, type RefObject } from 'react'

function doReveal(el: HTMLElement) {
  const delay = parseInt(el.dataset.delay || '0', 10)
  if (el.dataset.reveal === 'line') {
    const stagger = parseInt(el.dataset.lineStagger || '0', 10)
    el.querySelectorAll<HTMLElement>('.inner').forEach((n, i) => {
      n.style.transitionDelay = `${delay + i * stagger}ms`
    })
  } else if (delay) {
    el.style.transitionDelay = `${delay}ms`
  }
  // rAF로 트랜지션을 태우되, rAF가 멈춘 환경(백그라운드 탭 등)에서도
  // 텍스트가 영원히 숨겨지지 않도록 타이머 폴백을 함께 건다(중복 add는 무해).
  const show = () => el.classList.add('rv-in')
  requestAnimationFrame(show)
  setTimeout(show, 150)
}

/**
 * 프로토타입 리빌 엔진 포팅 — [data-reveal] 요소를 뷰포트 진입 시 표출.
 * data-gate="ready" 요소는 ready(로더 종료) 이후에만 표출.
 */
export function useReveal(ready: boolean, rootRef: RefObject<HTMLElement>) {
  const readyRef = useRef(ready)
  const pendingRef = useRef<HTMLElement[]>([])

  useEffect(() => {
    readyRef.current = ready
    if (ready) {
      pendingRef.current.forEach(doReveal)
      pendingRef.current = []
    }
  }, [ready])

  useEffect(() => {
    const root = rootRef.current
    if (!root) return
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return
          const el = entry.target as HTMLElement
          observer.unobserve(el)
          if (el.dataset.gate === 'ready' && !readyRef.current) {
            pendingRef.current.push(el)
            return
          }
          doReveal(el)
        })
      },
      { threshold: 0.15, rootMargin: '0px 0px -8% 0px' },
    )
    root.querySelectorAll<HTMLElement>('[data-reveal]').forEach((el) => observer.observe(el))
    return () => observer.disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}
