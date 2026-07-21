import { useEffect, useRef, type CSSProperties } from 'react'
import { Eyebrow } from '../../components/ui'

// landing.html 도입효과 — 스크롤 진행도에 비례하는 카운트업
const stats = [
  { value: 50, suf: '+', label: '도입 단지' },
  { value: 70, suf: '%↓', label: '인력 피로도' },
  { value: 98, suf: '%', label: '이벤트 감지율' },
  { value: 24, suf: '/7', label: '무중단 순찰' },
]

export function ImpactSection() {
  const numRefs = useRef<(HTMLSpanElement | null)[]>([])

  useEffect(() => {
    let last = 0
    const update = () => {
      const now = performance.now()
      if (now - last < 30) return
      last = now
      const vh = window.innerHeight
      numRefs.current.forEach((el, i) => {
        if (!el) return
        const r = el.getBoundingClientRect()
        const center = r.top + r.height / 2
        let p = (vh - center) / (vh - vh / 2)
        p = Math.max(0, Math.min(1, p))
        el.textContent = String(Math.round(p * stats[i].value))
      })
    }
    window.addEventListener('scroll', update, { passive: true })
    window.addEventListener('resize', update)
    update()
    return () => {
      window.removeEventListener('scroll', update)
      window.removeEventListener('resize', update)
    }
  }, [])

  return (
    <section id="impact">
      <div className="shell impact-inner">
        <div className="impact-panel" data-reveal="scale" style={{ '--ry': '40px' } as CSSProperties}>
          <div className="glow" />
          <Eyebrow tone="light">도입효과</Eyebrow>
          <h2 className="impact-h2" data-reveal="line" data-delay="120">
            <span className="line"><span className="inner">숫자로 증명되는 순찰의 변화</span></span>
          </h2>
          <ul className="impact-grid">
            {stats.map((s, i) => (
              <li key={s.label} data-reveal="up" data-delay={i * 90} style={{ '--ry': '20px' } as CSSProperties}>
                <div className="impact-num font-mono tabular">
                  <span ref={(el) => { numRefs.current[i] = el }}>0</span>
                  <span className="suf">{s.suf}</span>
                </div>
                <div className="impact-lbl">{s.label}</div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}
