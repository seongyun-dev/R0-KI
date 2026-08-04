import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { usePrefersReducedMotion } from '../../lib/usePrefersReducedMotion'
import { ROKI_BASE_YAW, animateRoki, buildRokiCourier } from './rokiCourierModel'

/* 로봇 상세 실시간 진단 — RO-KI 4륜 배송형 로봇 3/4 뷰 (S15P11E103-296).
   모델은 rokiCourierModel.ts. 랜딩 히어로(robotModel.ts 휴머노이드)와는 별개다.
   본체는 제자리 고정 — 부위 콜아웃 지시선이 화면 좌표에 붙어 있어 이동하면 어긋난다. */

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

function DiagnosticScene({ reduceMotion }: { reduceMotion: boolean }) {
  const { gl, scene } = useThree()
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

  // 리듀스드 모션 / 첫 프레임 정지 포즈
  useEffect(() => {
    model.root.rotation.y = ROKI_BASE_YAW
  }, [model])

  useFrame(({ clock }) => {
    if (reduceMotion) return
    const t = clock.elapsedTime
    animateRoki(model, t)

    // 바닥 광만 맥동 — 그림자는 제자리
    const pulse = 0.5 + Math.sin(t * 2.4) * 0.14
    ;(extras.pool.material as THREE.MeshBasicMaterial).opacity = pulse
    extras.pool.scale.set(1 + Math.sin(t * 2.4) * 0.04, 0.72, 1)
  })

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

export function RobotDiagnosticView({ className }: { className?: string }) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(true)
  const reduceMotion = usePrefersReducedMotion()

  // 뷰포트 밖이면 렌더 루프 정지
  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const io = new IntersectionObserver((es) => setVisible(es[0].isIntersecting), { threshold: 0.01 })
    io.observe(el)
    return () => io.disconnect()
  }, [])

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
        aria-label="RO-KI 순찰 로봇 진단 뷰"
      >
        <DiagnosticScene reduceMotion={reduceMotion} />
      </Canvas>
    </div>
  )
}
