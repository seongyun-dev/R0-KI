import { Suspense, lazy, useEffect, useRef, useState } from 'react'
import type { ProblemPhase, ScreenAnchor } from '../../components/robot/PatrolRobot'
import { Tag } from '../../components/ui'
import { cn } from '../../lib/cn'
import { usePrefersReducedMotion } from '../../lib/usePrefersReducedMotion'
import { BridgeSection } from './BridgeSection'
import { FeaturesSection } from './FeaturesSection'
import { Hero } from './Hero'
import { JOURNEY_STEPS } from './journeySteps'
import { ProblemSection } from './ProblemSection'

// three.js 청크 분리 — 첫 페인트(랜딩 텍스트/로더)를 막지 않게 lazy 로드
const PatrolRobot = lazy(() =>
  import('../../components/robot/PatrolRobot').then((m) => ({ default: m.PatrolRobot })),
)

const COUNT = 4
/** 한 구간에서 앞 45%는 이동, 이후는 도착 상태 */
const ARRIVE_AT = 0.45
/** 카드 우측 상단 기준 로봇 접지점 오프셋 — 모서리에 살짝 걸쳐 서게 한다 */
const ANCHOR_OFFSET = { x: -18, y: 10 }

type Ui = { solved: number; active: number; step: number }

/**
 * 히어로 → 해결하는 문제 → 기능을 캔버스 하나로 잇는 무대.
 * 로봇은 끊기지 않고 계속 이어진다:
 *   히어로에서 커서를 따라 순찰 → 문제 카드마다 찾아가 처리 → 그 지점들을 다시 돌며 기능 설명.
 */
function NarrativeStage({ ready }: { ready: boolean }) {
  const stageRef = useRef<HTMLDivElement>(null)
  const probRef = useRef<HTMLDivElement>(null)
  const jrnRef = useRef<HTMLDivElement>(null)

  const scrollProgress = useRef(0)
  const phaseRef = useRef<ProblemPhase>({ phase: -1, solved: -1 })
  const anchorRef = useRef<ScreenAnchor>({ x: 0, y: 0, active: false })
  /** 문제 카드 엘리먼트 캐시 — 매 프레임 DOM을 훑지 않도록 */
  const cardsRef = useRef<HTMLElement[]>([])
  /** 기능 구간 순찰 경로 진행률 (무대 → 씬) */
  const routeRef = useRef(-1)

  const [hintHidden, setHintHidden] = useState(false)
  const [inView, setInView] = useState(true)
  const [ui, setUi] = useState<Ui>({ solved: -1, active: -1, step: -1 })

  useEffect(() => {
    const el = stageRef.current
    if (!el) return
    const io = new IntersectionObserver((es) => setInView(es[0].isIntersecting), { threshold: 0 })
    io.observe(el)
    return () => io.disconnect()
  }, [])

  // 문제 카드 엘리먼트 캐시 (리사이즈 시 위치는 매 프레임 다시 재므로 목록만 갱신)
  useEffect(() => {
    const el = probRef.current
    if (!el) return
    cardsRef.current = [...el.querySelectorAll<HTMLElement>('.prob-card')]
  }, [])

  useEffect(() => {
    const stage = stageRef.current
    const prob = probRef.current
    const jrn = jrnRef.current
    if (!stage || !prob || !jrn || !inView) return

    let raf = 0
    const loop = () => {
      const vh = window.innerHeight

      // 무대 전체 진행률 → 카메라가 서서히 들린다
      const sr = stage.getBoundingClientRect()
      const sTotal = sr.height - vh
      scrollProgress.current = sTotal > 0 ? Math.min(1, Math.max(0, -sr.top / sTotal)) : 0

      // ── 기능 구간이 우선(뒤쪽 구간) ──
      const jr = jrn.getBoundingClientRect()
      const jTotal = jr.height - vh
      const jp = jTotal > 0 ? Math.min(1, Math.max(0, -jr.top / jTotal)) : 0
      // 기능 구간에 한 번 들어서면 계속 유지한다. bottom 조건을 걸면 구간을 지나쳤을 때
      // 다시 문제 모드로 잡혀 로봇이 화면 밖 카드로 되돌아간다.
      // 선행 구간을 짧게 잡아야(0.15) 앞의 전환 섹션이 제 몫의 시간을 갖는다.
      const inJourney = jr.top <= vh * 0.15

      // ── 문제 구간 ──
      const pr = prob.getBoundingClientRect()
      const pTotal = pr.height - vh
      const pp = pTotal > 0 ? Math.min(1, Math.max(0, -pr.top / pTotal)) : 0
      // 문제 구간을 지나면(전환 섹션) 커서 추적으로 돌아가 한 박자 쉰다
      const pastProblem = pr.bottom <= vh * 0.5
      const inProblem = !inJourney && !pastProblem && pr.top <= vh * 0.5

      let solved = -1
      let active = -1
      let step = -1

      if (inJourney) {
        // 해결했던 네 지점을 잇는 경로를 스크롤에 맞춰 주행한다
        routeRef.current = jp
        // 카드 전환은 스크롤에서 직접 계산한다. 씬이 알려주는 값에 기대면
        // 3D가 한 프레임이라도 못 돌 때(컨텍스트 유실·저사양·탭 비활성) 카드가 아예 안 뜬다.
        step = Math.min(COUNT - 1, Math.floor(jp * COUNT))
        phaseRef.current.phase = -1
        phaseRef.current.solved = COUNT
        anchorRef.current.active = false
        solved = COUNT
      } else if (inProblem) {
        // 한 문제당 한 구간(beat). 구간 안에서 이동 → 도착 → 그대로 정지,
        // 다음 구간이 시작돼야 비로소 다음 지점으로 출발한다(멈췄다 가는 순찰 리듬).
        // 끝(pp=1)에서 beat가 정확히 COUNT가 되면 나머지가 0이라 '이동중'으로 되돌아간다.
        // 마지막 구간 안쪽으로 살짝 당겨 마지막 지점에 머문 상태로 끝나게 한다.
        const beat = Math.min(pp * COUNT, COUNT - 1e-6)
        const idx = Math.min(COUNT - 1, Math.floor(beat))
        const arrived = beat % 1 >= ARRIVE_AT
        solved = Math.min(COUNT, Math.floor(beat) + (arrived ? 1 : 0))
        active = idx
        routeRef.current = -1
        phaseRef.current.phase = idx
        phaseRef.current.solved = solved
        // 로봇은 이번 카드의 우측 상단에 작게 서 있는다.
        // 구간이 바뀔 때만 다음 카드로 옮겨가므로 움직임이 짧고 잔잔하다.
        const card = cardsRef.current[idx]
        if (card) {
          const cr = card.getBoundingClientRect()
          anchorRef.current.x = cr.right + ANCHOR_OFFSET.x
          anchorRef.current.y = cr.top + ANCHOR_OFFSET.y
          anchorRef.current.active = true
        }
      } else if (pastProblem) {
        // 전환 구간 — 커서 추적으로 돌아가되, 처리한 문제는 해결 상태로 남겨둔다
        routeRef.current = -1
        phaseRef.current.phase = -1
        phaseRef.current.solved = COUNT
        anchorRef.current.active = false
        solved = COUNT
      } else {
        // 히어로 — 커서 추적
        anchorRef.current.active = false
        routeRef.current = -1
        phaseRef.current.phase = -1
        phaseRef.current.solved = -1
      }

      setUi((prev) =>
        prev.solved === solved && prev.active === active && prev.step === step
          ? prev
          : { solved, active, step },
      )
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [inView])

  return (
    <div ref={stageRef} className="patrol-stage">
      {/* 세 구간 뒤에 계속 떠 있는 하나의 순찰 장면 */}
      <div className="patrol-stage__scene" aria-hidden>
        {ready && (
          <Suspense fallback={null}>
            <PatrolRobot
              scrollRef={scrollProgress}
              problemRef={phaseRef}
              routeRef={routeRef}
              anchorRef={anchorRef}
              active={inView}
              onPointerActive={() => setHintHidden(true)}
            />
          </Suspense>
        )}
      </div>

      <Hero hintHidden={hintHidden} />

      {/* 해결하는 문제 — 로봇이 카드마다 찾아가 처리 */}
      <div ref={probRef} className="prob-track">
        <div className="prob-pin">
          <ProblemSection active={ui.active} solved={ui.solved} />
        </div>
      </div>

      {/* 문제 → 기능 전환 — 대응 관계를 정리하고 넘어간다 */}
      <BridgeSection />

      {/* 기능 — 처리했던 지점들을 다시 돌며 설명 */}
      <div ref={jrnRef} id="features" className="journey-track">
        <div className="journey-pin">
          <div className={cn('journey-lead-in', ui.step >= 0 && 'is-out')}>
            <p className="journey-eyebrow font-mono">[ 기능 ]</p>
            <h2>방금 그 네 곳을, 로봇이 매일 돕니다</h2>
          </div>

          {JOURNEY_STEPS.map((s, i) => (
            <article
              key={s.no}
              className={cn('journey-card', s.side === 'right' && 'is-right', ui.step === i && 'is-on')}
              aria-hidden={ui.step !== i}
            >
              <span className="journey-no font-mono tabular">[ {s.no} ]</span>
              <h3>{s.title}</h3>
              <p>{s.desc}</p>
              {/* 항목마다 받침이 달라 조사가 갈리므로 조사 없는 라벨 형태로 둔다 */}
              <p className="journey-answers">
                <span className="journey-answers__label">해결하는 문제</span>
                <span className="font-mono">{s.answers}</span>
              </p>
              <div className="journey-tags">
                {s.tags.map((t) => (
                  <Tag key={t} tone="dark">{t}</Tag>
                ))}
              </div>
            </article>
          ))}

          <ol className="journey-rail" aria-hidden>
            {JOURNEY_STEPS.map((s, i) => (
              <li key={s.no} className={cn(ui.step === i && 'is-on', ui.step > i && 'is-done')}>
                <span className="font-mono tabular">{s.no}</span>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </div>
  )
}

/** 모바일·모션 최소화 — 3D 히어로만 두고 나머지는 정적 섹션 */
function SimpleStage({ ready }: { ready: boolean }) {
  const [hintHidden, setHintHidden] = useState(false)
  return (
    <>
      <div className="patrol-stage patrol-stage--simple">
        <div className="patrol-stage__scene" aria-hidden>
          {ready && (
            <Suspense fallback={null}>
              <PatrolRobot onPointerActive={() => setHintHidden(true)} />
            </Suspense>
          )}
        </div>
        <Hero hintHidden={hintHidden} />
      </div>
      <ProblemSection />
      <FeaturesSection />
    </>
  )
}

export type PatrolStageProps = {
  /** 로더 종료 — 3D 씬은 ready 이후에만 마운트(첫 페인트 보호) */
  ready: boolean
}

export function PatrolStage({ ready }: PatrolStageProps) {
  const reduceMotion = usePrefersReducedMotion()
  // 첫 렌더부터 올바른 쪽을 그린다(폴백 깜빡임 방지).
  // 단, 레이아웃 전이라 innerWidth가 0으로 읽히는 경우가 있어 0이면 데스크톱으로 낙관한다.
  // 잘못 짚어도 아래 effect가 곧바로 바로잡는다.
  const [desktop, setDesktop] = useState(() => window.innerWidth === 0 || window.innerWidth >= 1024)

  useEffect(() => {
    // matchMedia change만으로는 0 → 실제 너비 전환을 놓칠 수 있어 resize도 함께 본다
    const sync = () => {
      if (window.innerWidth > 0) setDesktop(window.innerWidth >= 1024)
    }
    sync()
    const mq = window.matchMedia('(min-width: 1024px)')
    window.addEventListener('resize', sync)
    mq.addEventListener('change', sync)
    return () => {
      window.removeEventListener('resize', sync)
      mq.removeEventListener('change', sync)
    }
  }, [])

  const simple = reduceMotion || !desktop
  return simple ? <SimpleStage ready={ready} /> : <NarrativeStage ready={ready} />
}
