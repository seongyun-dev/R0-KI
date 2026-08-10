import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { usePrefersReducedMotion } from '../../lib/usePrefersReducedMotion'
import { animateRobotLife, buildRobot } from '../../components/robot/robotModel'
import type { ComplexMapData, MapCheckpoint, MapPin, Tone } from '../../types/domain'

/* 라이브 맵 3D 씬 (1h) — 랜딩 히어로의 순찰 로봇(robotModel.ts)이 백엔드 맵
   (구역·체크포인트) 위를 실제로 순찰한다. 체크포인트에 도착하면 잠시 멈춰
   점검하고, 지나간 경로는 주황 발자국으로 남는다. */

const COOL = new THREE.Color(0x5f6f9e)
const WARM = new THREE.Color(0xff6a30)
const TONE_HEX: Record<Tone, number> = {
  danger: 0xe5484d,
  warning: 0xd97706,
  success: 0x16a34a,
  info: 0x2563eb,
  neutral: 0x8a8a99,
}
const TRAIL_MAX = 400 // 지나간 경로 발자국 수 (한 바퀴 이상)

export type MapLiveSceneProps = {
  map: ComplexMapData
  checkpoints: MapCheckpoint[]
  pins: MapPin[]
  /** 긴급 핀 클릭 */
  onEmergencyClick?: () => void
  className?: string
}

/** 그리드 좌표 → 월드 좌표 (1칸 = 1유닛, 맵 중심 = 원점) */
function toWorld(map: ComplexMapData, gx: number, gy: number) {
  return { x: gx - map.cols / 2, z: gy - map.rows / 2 }
}

/** 맵 바닥 텍스처 — 그리드 + 구역 + 계획 경로(점선) + 체크포인트 라벨을 캔버스에 그린다 */
function floorTexture(map: ComplexMapData, checkpoints: MapCheckpoint[]) {
  const S = 96 // 1칸당 px
  const c = document.createElement('canvas')
  c.width = map.cols * S
  c.height = map.rows * S
  const g = c.getContext('2d')!

  g.fillStyle = '#0d0d10'
  g.fillRect(0, 0, c.width, c.height)

  // 그리드
  g.strokeStyle = 'rgba(255,255,255,0.07)'
  g.lineWidth = 2
  for (let i = 0; i <= map.cols; i++) {
    g.beginPath(); g.moveTo(i * S, 0); g.lineTo(i * S, c.height); g.stroke()
  }
  for (let i = 0; i <= map.rows; i++) {
    g.beginPath(); g.moveTo(0, i * S); g.lineTo(c.width, i * S); g.stroke()
  }

  // 구역
  for (const z of map.zones) {
    if (!z.rect) continue
    const { x, y, w, h } = z.rect
    g.fillStyle = 'rgba(255,255,255,0.05)'
    g.strokeStyle = 'rgba(255,255,255,0.14)'
    g.lineWidth = 3
    g.beginPath()
    g.roundRect(x * S + 6, y * S + 6, w * S - 12, h * S - 12, 16)
    g.fill()
    g.stroke()
    g.fillStyle = 'rgba(255,255,255,0.45)'
    g.font = `600 22px 'Pretendard Variable', Pretendard, sans-serif`
    g.fillText(z.label, x * S + 22, y * S + 40)
  }

  // 계획 경로 (점선) — 체크포인트 순환
  g.strokeStyle = 'rgba(37,99,235,0.85)'
  g.lineWidth = 5
  g.setLineDash([16, 12])
  g.beginPath()
  const loop = [...checkpoints, checkpoints[0]]
  loop.forEach((cp, i) => {
    const px = cp.x * S
    const py = cp.y * S
    if (i === 0) g.moveTo(px, py)
    else g.lineTo(px, py)
  })
  g.stroke()
  g.setLineDash([])

  // 체크포인트 아이콘 + 라벨
  for (const cp of checkpoints) {
    const px = cp.x * S
    const py = cp.y * S
    g.fillStyle = 'rgba(255,255,255,0.08)'
    g.beginPath(); g.arc(px, py, 26, 0, Math.PI * 2); g.fill()
    g.strokeStyle = 'rgba(255,255,255,0.25)'
    g.lineWidth = 2
    g.beginPath(); g.arc(px, py, 26, 0, Math.PI * 2); g.stroke()
    g.font = '26px sans-serif'
    g.textAlign = 'center'
    g.fillText(cp.icon, px, py + 9)
    g.font = `600 20px 'Pretendard Variable', Pretendard, sans-serif`
    g.fillStyle = 'rgba(255,255,255,0.75)'
    g.fillText(cp.label, px, py + 54)
    g.textAlign = 'left'
  }

  const t = new THREE.CanvasTexture(c)
  t.anisotropy = 4
  t.colorSpace = THREE.SRGBColorSpace
  return t
}

function LiveScene({ map, checkpoints, pins, onEmergencyClick, reduceMotion }: MapLiveSceneProps & { reduceMotion: boolean }) {
  const { gl, scene, camera, size } = useThree()

  const S = useMemo(() => {
    // ---- 로봇 (랜딩과 동일 모델 + LED 링) ----
    const model = buildRobot()
    model.robot.position.y = 1.55
    const rig = new THREE.Group()
    rig.add(model.robot)
    rig.scale.setScalar(0.42)
    const ledMat = new THREE.MeshStandardMaterial({
      color: 0x1a1a20, emissive: 0xff5a26, emissiveIntensity: 2.2, roughness: 0.35, metalness: 0.3,
    })
    model.baseRing.material = ledMat

    // ---- 바닥 ----
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(map.cols, map.rows),
      new THREE.MeshBasicMaterial({ map: floorTexture(map, checkpoints) }),
    )
    floor.rotation.x = -Math.PI / 2

    // ---- 지나간 경로 발자국 (주황, 잔존) ----
    const dotGeo = new THREE.CircleGeometry(0.075, 14)
    const trail = Array.from({ length: TRAIL_MAX }, () => {
      const m = new THREE.Mesh(
        dotGeo,
        new THREE.MeshBasicMaterial({ color: 0xff6a30, transparent: true, opacity: 0, depthWrite: false }),
      )
      m.rotation.x = -Math.PI / 2
      m.position.y = 0.02
      m.visible = false
      return m
    })

    // ---- 체크포인트 링 (근접 시 점등) ----
    const cps = checkpoints.map((cp) => {
      const { x, z } = toWorld(map, cp.x, cp.y)
      const grp = new THREE.Group()
      grp.position.set(x, 0.03, z)
      const ringMat = new THREE.MeshBasicMaterial({ color: 0x5f6f9e, transparent: true, opacity: 0.5 })
      const ring = new THREE.Mesh(new THREE.RingGeometry(0.34, 0.42, 36), ringMat)
      ring.rotation.x = -Math.PI / 2
      grp.add(ring)
      return { pos: new THREE.Vector3(x, 0, z), grp, ring, ringMat, lit: 0 }
    })

    // ---- 이벤트 핀 (긴급은 클릭 가능) ----
    const pinObjs = pins.map((p) => {
      const { x, z } = toWorld(map, p.x, p.y)
      const grp = new THREE.Group()
      grp.position.set(x, 0.05, z)
      const color = TONE_HEX[p.tone]
      const ringMat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.5 })
      const ring = new THREE.Mesh(new THREE.RingGeometry(0.16, 0.24, 28), ringMat)
      ring.rotation.x = -Math.PI / 2
      grp.add(ring)
      const dot = new THREE.Mesh(new THREE.CircleGeometry(0.13, 20), new THREE.MeshBasicMaterial({ color }))
      dot.rotation.x = -Math.PI / 2
      dot.position.y = 0.01
      grp.add(dot)
      return { pin: p, grp, ring, ringMat }
    })

    // ---- 순찰 상태 ----
    const first = checkpoints[0]
    const start = toWorld(map, first.x, first.y)
    const state = {
      pos: new THREE.Vector3(start.x, 0, start.z),
      vel: new THREE.Vector3(),
      tmp: new THREE.Vector3(),
      targetIdx: 1 % checkpoints.length,
      dwell: 0,
      lastDrop: new THREE.Vector3(start.x, 0, start.z),
      trailIdx: 0,
    }
    rig.position.set(start.x, 0, start.z)

    return { model, rig, ledMat, floor, trail, cps, pinObjs, state }
  }, [map, checkpoints, pins])

  // 환경 + 안개
  useEffect(() => {
    const pmrem = new THREE.PMREMGenerator(gl)
    const envTex = pmrem.fromScene(new RoomEnvironment(), 0.04).texture
    scene.environment = envTex
    scene.fog = new THREE.Fog(0x0a0a0a, 20, 34)
    return () => {
      scene.environment = null
      scene.fog = null
      envTex.dispose()
      pmrem.dispose()
    }
  }, [gl, scene])

  // 카메라 — 화면 비율에 맞춰 맵 전체가 보이게
  useEffect(() => {
    const aspect = size.width / Math.max(1, size.height)
    const f = Math.max(1, 2.1 / aspect)
    camera.position.set(0, 8.6 * f, 7.6 * f)
    camera.lookAt(0, 0, 0.3)
  }, [camera, size])

  useFrame(({ clock }, rawDt) => {
    if (reduceMotion) return
    const st = S.state
    const t = clock.elapsedTime

    // 프레임이 뜸한 환경(백그라운드 탭 복귀 등)에서도 순간이동 없이 따라잡도록
    // 최대 0.8초까지 0.05초 단위 서브스텝으로 적분한다.
    let acc = Math.min(rawDt, 0.8)
    while (acc > 0) {
      const dt = Math.min(acc, 0.05)
      acc -= dt

      // 체크포인트 도착 → 잠시 점검(정지) → 다음 목표
      const target = S.cps[st.targetIdx].pos
      if (st.dwell > 0) {
        st.dwell -= dt
        st.vel.multiplyScalar(0.85)
      } else {
        st.tmp.copy(target).sub(st.pos)
        st.tmp.y = 0
        const dist = st.tmp.length()
        if (dist < 0.35) {
          st.dwell = 1.2
          st.targetIdx = (st.targetIdx + 1) % S.cps.length
        } else {
          const speed = Math.min(2.1, dist * 1.6)
          st.tmp.normalize().multiplyScalar(speed)
          st.vel.lerp(st.tmp, 0.1)
        }
      }
      st.pos.addScaledVector(st.vel, dt)

      if (st.vel.length() > 0.1) {
        const heading = Math.atan2(st.vel.x, st.vel.z)
        let dh = heading - S.rig.rotation.y
        while (dh > Math.PI) dh -= 2 * Math.PI
        while (dh < -Math.PI) dh += 2 * Math.PI
        S.rig.rotation.y += dh * Math.min(1, dt * 7)
      }

      // 지나간 경로 발자국 — 잔존(서서히만 옅어짐)
      if (st.pos.distanceTo(st.lastDrop) > 0.3) {
        const d = S.trail[st.trailIdx % TRAIL_MAX]
        st.trailIdx++
        st.lastDrop.copy(st.pos)
        d.position.set(st.pos.x, 0.02, st.pos.z)
        d.visible = true
        ;(d.material as THREE.MeshBasicMaterial).opacity = 0.6
      }
      S.trail.forEach((d) => {
        const m = d.material as THREE.MeshBasicMaterial
        if (d.visible && m.opacity > 0.18) m.opacity -= dt * 0.012
      })
    }

    S.rig.position.set(st.pos.x, Math.sin(t * 3) * 0.02, st.pos.z)

    // 로봇 생동감 + LED 펄스
    animateRobotLife(S.model, t)
    S.ledMat.emissiveIntensity = 1.9 + Math.sin(t * 2.4) * 0.7

    // 체크포인트 점등
    S.cps.forEach((cp) => {
      const near = st.pos.distanceTo(cp.pos) < 1.1
      cp.lit += ((near ? 1 : 0) - cp.lit) * 0.12
      cp.ringMat.color.copy(COOL).lerp(WARM, cp.lit)
      cp.ring.scale.setScalar(1 + cp.lit * 0.5 + (near ? Math.sin(t * 6) * 0.05 : 0))
      cp.ringMat.opacity = 0.45 + cp.lit * 0.5
    })

    // 이벤트 핀 펄스 (긴급은 빠르게)
    S.pinObjs.forEach((p, i) => {
      const fast = p.pin.tone === 'danger'
      const k = Math.sin(t * (fast ? 3.6 : 2.2) + i) * 0.5 + 0.5
      p.ring.scale.setScalar(1 + k * (fast ? 1.1 : 0.6))
      p.ringMat.opacity = (fast ? 0.6 : 0.45) * (1 - k)
    })
  })

  return (
    <>
      <primitive object={S.floor} />
      {S.trail.map((d, i) => (
        <primitive key={i} object={d} />
      ))}
      {S.cps.map((cp, i) => (
        <primitive key={`cp${i}`} object={cp.grp} />
      ))}
      {S.pinObjs.map((p) => (
        <primitive
          key={p.pin.id}
          object={p.grp}
          onClick={p.pin.tone === 'danger' ? onEmergencyClick : undefined}
        />
      ))}
      {/* 긴급 핀 클릭 히트 영역(넉넉하게) */}
      {S.pinObjs
        .filter((p) => p.pin.tone === 'danger')
        .map((p) => (
          <mesh
            key={`hit-${p.pin.id}`}
            position={[p.grp.position.x, 0.06, p.grp.position.z]}
            rotation={[-Math.PI / 2, 0, 0]}
            onClick={onEmergencyClick}
            onPointerOver={() => (gl.domElement.style.cursor = 'pointer')}
            onPointerOut={() => (gl.domElement.style.cursor = '')}
          >
            <circleGeometry args={[0.8, 24]} />
            <meshBasicMaterial transparent opacity={0} depthWrite={false} />
          </mesh>
        ))}
      <primitive object={S.rig} />
      <hemisphereLight args={[0xffffff, 0x30303a, 0.5]} />
      <directionalLight color={0xffffff} intensity={1.8} position={[-3, 6, 5]} />
      <directionalLight color={0xff7a45} intensity={1.2} position={[4, 2, -3]} />
      <directionalLight color={0xdfe6ff} intensity={0.4} position={[3, 3, 4]} />
    </>
  )
}

export function MapLiveScene({ className, ...props }: MapLiveSceneProps) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(true)
  const reduceMotion = usePrefersReducedMotion()

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
        camera={{ fov: 40, near: 0.1, far: 60, position: [0, 8.6, 7.6] }}
        gl={{ antialias: true, alpha: true }}
        onCreated={({ gl }) => {
          gl.setClearColor(0x000000, 0)
          gl.toneMapping = THREE.ACESFilmicToneMapping
          gl.toneMappingExposure = 1.12
        }}
        aria-label="라이브 맵 — 순찰 로봇이 체크포인트를 따라 이동 중"
      >
        {/* 체크포인트가 없으면 순찰 경로의 첫 지점을 잡을 수 없어 씬을 구성하다 터진다.
            없는 지점을 지어내는 대신 씬을 아예 올리지 않는다 — 호출측이 빈 안내를 띄운다. */}
        {props.checkpoints.length > 0 && <LiveScene {...props} reduceMotion={reduceMotion} />}
      </Canvas>
    </div>
  )
}

export default MapLiveScene
