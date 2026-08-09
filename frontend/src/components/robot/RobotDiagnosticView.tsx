import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { usePrefersReducedMotion } from '../../lib/usePrefersReducedMotion'
import { ROKI_BASE_YAW, animateRoki, buildRokiCourier } from './rokiCourierModel'
import { type ProjectedAnchor, projectPartAnchors } from './rokiLeaders'

/* 로봇 상세 실시간 진단 — RO-KI 4륜 배송형 로봇 3/4 뷰 (S15P11E103-296).
   모델은 rokiCourierModel.ts. 랜딩 히어로(robotModel.ts 휴머노이드)와는 별개다.

   드래그 · 가로 스크롤(트랙패드) · 터치로 360° 돌려 앞뒤를 볼 수 있고,
   손을 떼고 잠시 두면 천천히 자전한다.
   회전하면 부위가 화면에서 움직이므로 콜아웃 지시선을 CSS 고정 좌표로 둘 수 없다 —
   매 프레임 부위 좌표를 투영해 onAnchors 로 넘기고, 지시선은 상위(RobotDetail)가 그린다. */

export type RobotDiagnosticViewProps = {
  className?: string
  /** 매 프레임(약 30fps로 스로틀) 부위 투영 좌표를 넘긴다. 지시선을 그리는 쪽이 받는다 */
  onAnchors?: (anchors: ProjectedAnchor[]) => void
}

/** 부드러운 원형 그라데이션 텍스처 (접지 그림자 / LED 광 웅덩이) */
function radialTexture(inner: string, mid: string) {
  const c = document.createElement('canvas')
  c.width = c.height = 256
  const g = c.getContext('2d')!
  const grd = g.createRadialGradient(128, 128, 0, 128, 128, 128)
  grd.addColorStop(0, inner)
  grd.addColorStop(0.55, mid)
  grd.addColorStop(1, 'rgba(0,0,0,0)')
  g.fillStyle = grd
  g.fillRect(0, 0, 256, 256)
  return new THREE.CanvasTexture(c)
}

/** 휠 바닥 y — 그림자/광 웅덩이를 여기 맞춰 깔아야 로봇이 떠 보이지 않는다 */
const FLOOR_Y = -1.63
/** 손을 뗀 뒤 자전이 다시 붙기까지 */
const IDLE_SPIN_DELAY = 3.5
/** 자전 속도(rad/s) — 한 바퀴에 약 35초. 빠르면 지시선이 산만해진다 */
const IDLE_SPIN_SPEED = 0.18

function DiagnosticScene({
  reduceMotion,
  yawRef,
  spinRef,
  onAnchors,
}: {
  reduceMotion: boolean
  yawRef: React.MutableRefObject<number>
  spinRef: React.MutableRefObject<{ velocity: number; lastInput: number; dragging: boolean }>
  onAnchors?: (anchors: ProjectedAnchor[]) => void
}) {
  const { gl, scene, size } = useThree()
  const model = useMemo(buildRokiCourier, [])

  // 흰 배경용 접지 연출 — 그림자 + 은은한 진단 광
  const extras = useMemo(() => {
    const shadow = new THREE.Mesh(
      new THREE.CircleGeometry(2.3, 48),
      new THREE.MeshBasicMaterial({
        map: radialTexture('rgba(15,18,22,0.30)', 'rgba(15,18,22,0.10)'),
        transparent: true,
        depthWrite: false,
      }),
    )
    shadow.rotation.x = -Math.PI / 2
    shadow.position.y = FLOOR_Y - 0.01
    shadow.scale.set(1, 0.72, 1)
    shadow.renderOrder = 1

    // 진단 중임을 읽히게 하는 바닥 광 — 셸이 흰색이라 세게 깔면 바로 탁해진다
    const pool = new THREE.Mesh(
      new THREE.CircleGeometry(1.9, 48),
      new THREE.MeshBasicMaterial({
        map: radialTexture('rgba(53,172,248,0.55)', 'rgba(53,172,248,0.20)'),
        transparent: true,
        depthWrite: false,
      }),
    )
    pool.rotation.x = -Math.PI / 2
    pool.position.y = FLOOR_Y - 0.02
    pool.scale.set(1, 0.72, 1)
    pool.renderOrder = 0

    return { shadow, pool }
  }, [])

  const lastEmit = useRef(0)

  useEffect(() => {
    const pmrem = new THREE.PMREMGenerator(gl)
    const envTex = pmrem.fromScene(new RoomEnvironment(), 0.04).texture
    scene.environment = envTex
    return () => {
      scene.environment = null
      envTex.dispose()
      pmrem.dispose()
    }
  }, [gl, scene])

  const emitAnchors = useCallback(
    (camera: THREE.Camera) => {
      if (!onAnchors) return
      onAnchors(projectPartAnchors(model.root, camera))
    },
    [model, onAnchors],
  )

  // 리듀스드 모션 — 정지 포즈에서도 지시선은 맞춰 둬야 한다
  useEffect(() => {
    if (!reduceMotion) return
    model.root.rotation.y = yawRef.current
    model.root.updateMatrixWorld()
  }, [reduceMotion, model, yawRef])

  useFrame(({ clock, camera }, rawDt) => {
    if (reduceMotion) return
    const t = clock.elapsedTime
    const dt = Math.min(rawDt, 0.05)
    const spin = spinRef.current
    /* 입력 시각(lastInput)은 포인터/휠 핸들러가 performance.now() 기준으로 찍는다.
       clock.elapsedTime 은 캔버스 마운트 기준이라 두 값을 섞으면 자동 회전이 영영 안 걸린다. */
    const nowSec = performance.now() / 1000

    if (spin.dragging) {
      // 드래그 중에는 포인터가 각도를 직접 몰고, 관성만 쌓아 둔다
    } else {
      // 관성 감쇠 — 손을 떼면 미끄러지듯 멈춘다
      yawRef.current += spin.velocity
      spin.velocity *= 0.92
      if (Math.abs(spin.velocity) < 0.0004) spin.velocity = 0

      // 한동안 입력이 없으면 천천히 자전 (앞뒤를 저절로 보여준다)
      if (spin.velocity === 0 && nowSec - spin.lastInput > IDLE_SPIN_DELAY) {
        yawRef.current += IDLE_SPIN_SPEED * dt
      }
    }

    animateRoki(model, t, yawRef.current)

    // 바닥 광만 맥동 — 그림자는 제자리
    const pulse = 0.5 + Math.sin(t * 2.4) * 0.14
    ;(extras.pool.material as THREE.MeshBasicMaterial).opacity = pulse
    extras.pool.scale.set(1 + Math.sin(t * 2.4) * 0.04, 0.72, 1)

    // 지시선 갱신 — 60fps로 DOM을 만지면 낭비라 30fps로 스로틀
    if (t - lastEmit.current > 1 / 30) {
      lastEmit.current = t
      emitAnchors(camera)
    }
  })

  // 리사이즈 직후에도 지시선이 따라오도록 한 번 갱신
  const { camera } = useThree()
  useEffect(() => {
    emitAnchors(camera)
  }, [emitAnchors, camera, size.width, size.height])

  return (
    <>
      <primitive object={extras.pool} />
      <primitive object={extras.shadow} />
      <primitive object={model.root} />
      {/* 흰 셸이라 정면광을 세게 주면 바로 날아간다 — 키라이트를 낮추고 환경광에 맡긴다 */}
      <hemisphereLight args={[0xffffff, 0xd8e2f0, 0.55]} />
      <directionalLight color={0xffffff} intensity={1.45} position={[-3.4, 4.6, 5]} />
      <directionalLight color={0x9ec9f5} intensity={0.75} position={[4, -0.6, -3]} />
      <directionalLight color={0xeef3ff} intensity={0.4} position={[3.4, 2.4, 4]} />
    </>
  )
}

export function RobotDiagnosticView({ className, onAnchors }: RobotDiagnosticViewProps) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(true)
  const reduceMotion = usePrefersReducedMotion()

  const yawRef = useRef(ROKI_BASE_YAW)
  // lastInput 은 performance.now() 초 단위 — 0으로 두면 마운트 직후부터 자전이 걸린다
  const spinRef = useRef({ velocity: 0, lastInput: performance.now() / 1000, dragging: false })

  // 뷰포트 밖이면 렌더 루프 정지
  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const io = new IntersectionObserver((es) => setVisible(es[0].isIntersecting), { threshold: 0.01 })
    io.observe(el)
    return () => io.disconnect()
  }, [])

  /* 회전 입력 — 드래그(마우스·터치·펜)와 트랙패드 가로 스크롤.
     wheel 은 passive:false 여야 preventDefault 가 먹어서 페이지가 같이 밀리지 않는다.
     세로 스크롤은 건드리지 않는다(페이지가 스크롤돼야 하므로). */
  useEffect(() => {
    const el = wrapRef.current
    if (!el || reduceMotion) return

    let lastX = 0
    let lastMoveAt = 0

    const now = () => performance.now() / 1000

    const onPointerDown = (e: PointerEvent) => {
      if (e.button != null && e.button !== 0) return
      spinRef.current.dragging = true
      spinRef.current.velocity = 0
      spinRef.current.lastInput = now()
      lastX = e.clientX
      lastMoveAt = now()
      el.setPointerCapture?.(e.pointerId)
    }

    const onPointerMove = (e: PointerEvent) => {
      if (!spinRef.current.dragging) return
      const dx = e.clientX - lastX
      lastX = e.clientX
      const step = dx * 0.009
      yawRef.current += step
      // 놓았을 때 이어질 관성 — 프레임 간격이 들쭉날쭉해도 튀지 않게 눌러둔다
      const dtMove = Math.max(1 / 120, now() - lastMoveAt)
      lastMoveAt = now()
      spinRef.current.velocity = THREE.MathUtils.clamp(step * (1 / 60 / dtMove), -0.12, 0.12)
      spinRef.current.lastInput = now()
    }

    const endDrag = (e: PointerEvent) => {
      if (!spinRef.current.dragging) return
      spinRef.current.dragging = false
      spinRef.current.lastInput = now()
      el.releasePointerCapture?.(e.pointerId)
    }

    const onWheel = (e: WheelEvent) => {
      // 가로 성분이 더 클 때만 회전으로 받는다 — 세로 휠은 페이지 스크롤로 흘려보낸다
      if (Math.abs(e.deltaX) <= Math.abs(e.deltaY)) return
      e.preventDefault()
      // 트랙패드 자연 스크롤은 손가락을 오른쪽으로 밀면 deltaX 가 음수다.
      // 그대로 더하면 손가락과 반대로 돌아가므로 부호를 뒤집는다(드래그와 방향이 맞는다).
      yawRef.current -= e.deltaX * 0.004
      spinRef.current.velocity = 0
      spinRef.current.lastInput = now()
    }

    el.addEventListener('pointerdown', onPointerDown)
    el.addEventListener('pointermove', onPointerMove)
    el.addEventListener('pointerup', endDrag)
    el.addEventListener('pointercancel', endDrag)
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => {
      el.removeEventListener('pointerdown', onPointerDown)
      el.removeEventListener('pointermove', onPointerMove)
      el.removeEventListener('pointerup', endDrag)
      el.removeEventListener('pointercancel', endDrag)
      el.removeEventListener('wheel', onWheel)
    }
  }, [reduceMotion])

  return (
    <div ref={wrapRef} className={className}>
      <Canvas
        dpr={[1, 2]}
        frameloop={reduceMotion || !visible ? 'demand' : 'always'}
        camera={{ fov: 35, near: 0.1, far: 50, position: [0, 2.3, 6.7] }}
        gl={{ antialias: true, alpha: true }}
        onCreated={({ gl, camera }) => {
          gl.setClearColor(0x000000, 0)
          gl.toneMapping = THREE.ACESFilmicToneMapping
          gl.toneMappingExposure = 1.0
          camera.lookAt(0, 0.05, 0)
        }}
        aria-label="RO-KI 순찰 로봇 진단 뷰 — 좌우로 끌면 회전합니다"
      >
        <DiagnosticScene
          reduceMotion={reduceMotion}
          yawRef={yawRef}
          spinRef={spinRef}
          onAnchors={onAnchors}
        />
      </Canvas>
    </div>
  )
}
