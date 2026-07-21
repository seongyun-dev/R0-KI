import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { usePrefersReducedMotion } from '../../lib/usePrefersReducedMotion'
import { animateRobotLife, buildRobot } from './robotModel'

/* 로봇 상세 [ LIVE DIAGNOSTICS ] — 정면 45° 뷰 프리뷰 (1i).
   랜딩 히어로와 같은 로봇 모델(robotModel.ts)을 재사용.
   흰 배경 위에서 좌우로 순찰하듯 이동하고, 베이스 링은 LED로 발광한다. */

/** 부드러운 원형 그라데이션 텍스처 (LED 광 웅덩이 / 접지 그림자) */
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

function DiagnosticScene({ reduceMotion }: { reduceMotion: boolean }) {
  const { gl, scene } = useThree()
  const model = useMemo(buildRobot, [])

  // 흰 배경용 보정 + LED 링 + 바닥 레이어 (로봇 본체는 그대로)
  const extras = useMemo(() => {
    // 베이스 링 → LED 발광 재질로 교체
    const ledMat = new THREE.MeshStandardMaterial({
      color: 0x1a1a20,
      emissive: 0xff5a26,
      emissiveIntensity: 2.2,
      roughness: 0.35,
      metalness: 0.3,
    })
    model.baseRing.material = ledMat

    // LED가 바닥에 비치는 광 웅덩이
    const pool = new THREE.Mesh(
      new THREE.CircleGeometry(1.6, 48),
      new THREE.MeshBasicMaterial({
        map: radialTexture('rgba(255,106,48,0.9)', 'rgba(255,106,48,0.35)'),
        transparent: true,
        depthWrite: false,
      }),
    )
    pool.rotation.x = -Math.PI / 2
    pool.position.y = -1.58
    pool.renderOrder = 2

    // 접지 그림자 — 흰 배경에서 입체감을 잡아준다
    const shadow = new THREE.Mesh(
      new THREE.CircleGeometry(2.1, 48),
      new THREE.MeshBasicMaterial({
        map: radialTexture('rgba(20,18,15,0.32)', 'rgba(20,18,15,0.12)'),
        transparent: true,
        depthWrite: false,
      }),
    )
    shadow.rotation.x = -Math.PI / 2
    shadow.position.y = -1.62
    shadow.renderOrder = 1

    // 바이저 글로우 스프라이트는 가산 블렌딩이라 흰 배경에서 사라짐 → 일반 블렌딩으로
    model.glow.material.blending = THREE.NormalBlending
    model.glow2.material.blending = THREE.NormalBlending

    return { ledMat, pool, shadow }
  }, [model])

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

  // 정면에서 45° 돌아간 기본 포즈
  useEffect(() => {
    model.robot.rotation.y = Math.PI / 4
  }, [model])

  useFrame(({ clock }) => {
    if (reduceMotion) return
    const t = clock.elapsedTime
    animateRobotLife(model, t)

    // 좌우 순찰 글라이드 — 이동 방향으로 몸을 살짝 틀고(입체감) 얕은 타원 궤적
    const g = t * 0.45
    const x = Math.sin(g) * 1.15
    const z = Math.cos(g * 2) * 0.18
    model.robot.position.set(x, Math.sin(t * 1.6) * 0.05, z)
    model.robot.rotation.y = Math.PI / 4 + Math.cos(g) * 0.28

    // LED 펄스 + 바닥 광/그림자가 로봇을 따라감
    extras.ledMat.emissiveIntensity = 1.9 + Math.sin(t * 2.4) * 0.7
    const pulse = 0.55 + Math.sin(t * 2.4) * 0.15
    ;(extras.pool.material as THREE.MeshBasicMaterial).opacity = pulse
    extras.pool.position.set(x, -1.58, z)
    extras.pool.scale.setScalar(1 + Math.sin(t * 2.4) * 0.06)
    extras.shadow.position.set(x, -1.62, z)
  })

  return (
    <>
      <primitive object={extras.shadow} />
      <primitive object={extras.pool} />
      <primitive object={model.robot} />
      <hemisphereLight args={[0xffffff, 0x8a8a8a, 0.65]} />
      <directionalLight color={0xffffff} intensity={2.1} position={[-3, 4, 5]} />
      <directionalLight color={0xff7a45} intensity={1.4} position={[4, -1, -3]} />
      <directionalLight color={0xdfe6ff} intensity={0.5} position={[3, 2, 4]} />
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
        camera={{ fov: 35, near: 0.1, far: 50, position: [0, 0.7, 9.6] }}
        gl={{ antialias: true, alpha: true }}
        onCreated={({ gl, camera }) => {
          gl.setClearColor(0x000000, 0)
          gl.toneMapping = THREE.ACESFilmicToneMapping
          gl.toneMappingExposure = 1.12
          camera.lookAt(0, 0.3, 0)
        }}
        aria-label="R-01 정면 45° 진단 뷰"
      >
        <DiagnosticScene reduceMotion={reduceMotion} />
      </Canvas>
    </div>
  )
}
