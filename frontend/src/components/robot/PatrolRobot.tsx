import { useEffect, useMemo, useRef, useState, type MutableRefObject } from 'react'
import * as THREE from 'three'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { usePrefersReducedMotion } from '../../lib/usePrefersReducedMotion'
import { ROBOT_ACCENT_LANDING, animateRobotLife, buildRobot } from './robotModel'
import { gridTexture, shadowTexture } from './sceneTextures'
import { animateRoki, buildRokiCourier } from './rokiCourierModel'

/* ============================================================
   랜딩 히어로 3D 순찰 로봇 — docs/reference/landing.html의 Three.js
   씬(맵·순찰 경로·커서 추적·액센트 트레일)을 R3F로 포팅.
   로봇 본체 지오메트리는 robotModel.ts에서 공유. 수치는 프로토타입 그대로.
   ============================================================ */

const TRAIL_COUNT = 34
/* 대기 상태 체크포인트 — 쿨톤 남색. 진하지 않게 눌러둬야 로봇이 지나며 켜지는
   LIT(밝은 하늘색)와 명도가 갈려 "꺼짐 → 켜짐"이 읽힌다. */
const COOL = new THREE.Color(0x5b729f)
/* 로봇이 지나며 점등되는 색 — 랜딩 액센트(#38BDF8)와 같은 계열 (S15P11E103-276) */
const LIT = new THREE.Color(0x38bdf8)
// 문제 지점 상태색 — 미해결(danger) → 해결(파랑).
// 해결은 초록 대신 진한 파랑. LIT(밝은 파랑)와 명도가 갈려 점등 연출이 그대로 살아난다.
const UNSOLVED = new THREE.Color(0xe11d48)
const SOLVED = new THREE.Color(0x0284c7)

/** 로봇이 문제를 하나씩 처리하는 진행 상태 (해결하는 문제 섹션) */
export type ProblemPhase = {
  /** 지금 향하는 문제 지점 (-1이면 커서 추적 모드) */
  phase: number
  /** 해결 완료한 문제 수 */
  solved: number
}

/**
 * 로봇을 화면상의 한 지점(문제 카드 우측 상단)에 세우기 위한 앵커.
 * 화면 좌표를 지면으로 역투영해 목표로 삼고, 이때는 로봇을 작게 줄인다.
 */
export type ScreenAnchor = {
  /** 뷰포트 기준 좌표(px) */
  x: number
  y: number
  /** 앵커를 따를지 여부 */
  active: boolean
}

/** 카드 옆에 설 때의 축소 배율 (기본 0.62) */
const MINI_SCALE = 0.3
const BASE_SCALE = 0.62

type SceneState = ReturnType<typeof buildScene>

function buildScene() {

  // ---- 로봇 본체 (robotModel.ts 공유) ----
  // 랜딩은 액센트가 블루라 눈·글로우도 블루로 넘긴다. 관제 화면은 기본값(주황) 유지.
  const root = new THREE.Group()

  // ---- RO-KI Courier ----
  const model = buildRokiCourier()

  const rig = new THREE.Group()
  rig.add(model.root)
  rig.scale.setScalar(0.62)
  root.add(rig)

  // ---- ground map + contact shadow ----

  // ---- ground map + contact shadow ----
  // 지면은 조명·톤매핑을 타지 않는 basic 재질로 둔다.
  // ACES 톤매핑(gl.toneMapping)은 밝은 값을 눌러서, standard 재질이면 텍스처에 넣은 색보다
  // 어둡게 렌더된다 — 페이지 배경과 캔버스 영역이 한 줄로 갈리는 원인.
  // toneMapped:false + 무광 basic 이면 gridTexture 의 색이 그대로 나와 배경과 정확히 이어진다.
  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(120, 120),
    new THREE.MeshBasicMaterial({ color: 0xffffff, map: gridTexture(), toneMapped: false }),
  )
  ground.rotation.x = -Math.PI / 2
  root.add(ground)
  const shadow = new THREE.Mesh(
    new THREE.PlaneGeometry(2.6, 2.6),
    new THREE.MeshBasicMaterial({ map: shadowTexture(), transparent: true, depthWrite: false }),
  )
  shadow.rotation.x = -Math.PI / 2
  shadow.position.y = 0.03
  root.add(shadow)

  // ---- 순찰 트레일 (액센트 블루) ----
  const trailGeo = new THREE.CircleGeometry(0.16, 18)
  const trail = Array.from({ length: TRAIL_COUNT }, () => {
    // 트레일은 --accent(#38BDF8) 하늘색 — 로봇 눈·순찰 경로선과 같은 브랜드 파랑이라
    // 씬 전체가 한 계열로 묶인다. 지면(GROUND_TINT)이 옅은 하늘이라 대비도 충분하다.
    const mat = new THREE.MeshBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0, depthWrite: false })
    const mesh = new THREE.Mesh(trailGeo, mat)
    mesh.rotation.x = -Math.PI / 2
    mesh.position.y = 0.02
    mesh.visible = false
    root.add(mesh)
    return { mesh, mat, age: 1e9 }
  })

  // ---- checkpoints ----
  // 화면에서 순찰 경로가 시원하게 보이도록 넉넉히 벌려둔다.
  // 좌우 부호가 카드 배치(journeySteps.side)와 반대여야 로봇이 카드에 가리지 않는다.
  const cpPos = [
    new THREE.Vector3(-7.5, 0, -4.4), // 01 — 좌측
    new THREE.Vector3(5.6, 0, -5.6), // 02 — 우측
    new THREE.Vector3(8.1, 0, 3.8), // 03 — 우측
    new THREE.Vector3(-5, 0, 5.6), // 04 — 좌측
  ]
  const checkpoints = cpPos.map((p) => {
    const grp = new THREE.Group()
    grp.position.set(p.x, 0.05, p.z)
    const ringMat = new THREE.MeshBasicMaterial({ color: 0x5f6f9e, transparent: true, opacity: 0.3 })
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.4, 0.5, 36), ringMat)
    ring.rotation.x = -Math.PI / 2
    grp.add(ring)
    const dotMat = new THREE.MeshBasicMaterial({ color: 0x5f6f9e, transparent: true, opacity: 0.6 })
    const dot = new THREE.Mesh(new THREE.CircleGeometry(0.14, 24), dotMat)
    dot.rotation.x = -Math.PI / 2
    dot.position.y = 0.01
    grp.add(dot)
    root.add(grp)
    // solvedAmt: 문제 해결 연출용 0→1 (해결하는 문제 섹션에서만 사용)
    return { pos: p, ring, ringMat, dotMat, lit: 0, solvedAmt: 0 }
  })

  // ---- event ping (불법주차 칩과 호응) ----
  const evGrp = new THREE.Group()
  evGrp.position.set(-1.5, 0.06, -2.0)
  const evRingMat = new THREE.MeshBasicMaterial({ color: 0xe11d48, transparent: true, opacity: 0.3 })
  const evRing = new THREE.Mesh(new THREE.RingGeometry(0.18, 0.26, 28), evRingMat)
  evRing.rotation.x = -Math.PI / 2
  evGrp.add(evRing)
  const evDot = new THREE.Mesh(new THREE.CircleGeometry(0.15, 20), new THREE.MeshBasicMaterial({ color: 0xe11d48, transparent: true, opacity: 0.55 }))
  evDot.rotation.x = -Math.PI / 2
  evDot.position.y = 0.01
  evGrp.add(evDot)
  root.add(evGrp)

  // ---- 기능 구간 순찰 경로 ----
  // 단지를 크게 휘돌되 문제를 해결했던 네 지점(cpPos)을 반드시 지난다.
  // 체크포인트 사이에 중간 경유점을 넣어 실제 순찰처럼 굽이치게 만든다.
  const routeCurve = new THREE.CatmullRomCurve3(
    [
      cpPos[0].clone(), // 01 지점
      new THREE.Vector3(-1.2, 0, -7.0),
      cpPos[1].clone(), // 02 지점
      new THREE.Vector3(9.5, 0, -1.2),
      cpPos[2].clone(), // 03 지점
      new THREE.Vector3(1.9, 0, 7.2),
      cpPos[3].clone(), // 04 지점
      new THREE.Vector3(-11.0, 0, 1.2),
    ],
    true,
    'catmullrom',
    0.5,
  )
  const routeSeg = 260
  const routePts = routeCurve.getSpacedPoints(routeSeg).map((p) => new THREE.Vector3(p.x, 0.035, p.z))
  const plannedMat = new THREE.LineBasicMaterial({ color: 0x8b93ab, transparent: true, opacity: 0 })
  const plannedLine = new THREE.Line(new THREE.BufferGeometry().setFromPoints(routePts), plannedMat)
  root.add(plannedLine)
  const doneGeo = new THREE.BufferGeometry().setFromPoints(routePts)
  doneGeo.setDrawRange(0, 0)
  const doneMat = new THREE.LineBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0 })
  root.add(new THREE.Line(doneGeo, doneMat))

  // 각 체크포인트를 지나는 경로 진행률 (카드 전환 타이밍의 기준)
  const checkpointT = cpPos.map((p) => {
    let bestT = 0
    let bestD = Infinity
    for (let i = 0; i <= 400; i++) {
      const t = i / 400
      const q = routeCurve.getPointAt(t)
      const d = (q.x - p.x) ** 2 + (q.z - p.z) ** 2
      if (d < bestD) {
        bestD = d
        bestT = t
      }
    }
    return bestT
  })

  // ---- mutable sim state ----
  const state = {
    target: new THREE.Vector3(4, 0, 0),
    botPos: new THREE.Vector3(4, 0, 0),
    vel: new THREE.Vector3(),
    tmp: new THREE.Vector3(),
    lastDrop: new THREE.Vector3(9999, 0, 0),
    camGoal: new THREE.Vector3(),
    trailIdx: 0,
    lastPointer: -1e9,
    time: 0,
  }
  // 초기 정지 포즈(리듀스드 모션 대비)
  rig.position.set(state.botPos.x, 0, state.botPos.z)
  shadow.position.set(state.botPos.x, 0.03, state.botPos.z)

  return {
    root, rig, model, shadow, trail, checkpoints, evRing, evRingMat, state,
    routeCurve, routeSeg, doneGeo, plannedMat, doneMat, checkpointT,
  }
}

function RobotScene({
  reduceMotion,
  onPointerActive,
  scrollRef,
  problemRef,
  routeRef,
  anchorRef,
}: {
  reduceMotion: boolean
  onPointerActive?: () => void
  scrollRef?: MutableRefObject<number>
  problemRef?: MutableRefObject<ProblemPhase>
  routeRef?: MutableRefObject<number>
  anchorRef?: MutableRefObject<ScreenAnchor>
}) {
  const { camera, gl, scene, size } = useThree()
  const S = useMemo<SceneState>(buildScene, [])
  const followCamRef = useRef(false)
  const pointerActiveRef = useRef(false)
  // 리사이즈에서 계산한 기본 카메라 (스크롤 오프셋의 기준점)
  const camBase = useRef({ pos: new THREE.Vector3(0, 8.6, 12.2), look: new THREE.Vector3(0, 0.3, -1.5) })
  const camTmp = useRef(new THREE.Vector3())
  const lookTmp = useRef(new THREE.Vector3())
  // 경로 주행용 임시 벡터
  const routePos = useRef(new THREE.Vector3())
  const routeTan = useRef(new THREE.Vector3())
  // 화면 좌표 → 지면 역투영 (카드 우측 상단에 세울 때)
  const caster = useRef(new THREE.Raycaster())
  const ground = useRef(new THREE.Plane(new THREE.Vector3(0, 1, 0), 0))
  const ndc = useRef(new THREE.Vector2())
  const hitPt = useRef(new THREE.Vector3())

  // environment (RoomEnvironment — 네트워크 불필요)
  useEffect(() => {
    const pmrem = new THREE.PMREMGenerator(gl)
    const envTex = pmrem.fromScene(new RoomEnvironment(), 0.04).texture
    scene.environment = envTex
    // 안개는 먼 지면을 배경색으로 녹인다 — 하늘 톤이 아니면 화면 전체가 그 색으로 읽힌다.
    // 문제·기능 구간은 지면이 시야를 가득 채우므로 이 값이 사실상 그 화면의 배경색이다.
    // 페이지 하늘(--page 계열)보다 밝으면 무대가 끝나는 지점에서 경계가 한 줄로 드러나므로
    // 하늘 중간 톤에 맞춘다.
    scene.fog = new THREE.Fog(0xe1edfa, 15, 42)
    return () => {
      scene.environment = null
      scene.fog = null
      envTex.dispose()
      pmrem.dispose()
    }
  }, [gl, scene])

  // 리사이즈 — 세로 비율이면 로봇 추적 카메라 (프로토타입 sizeAll)
  useEffect(() => {
    const cam = camera as THREE.PerspectiveCamera
    const aspect = size.width / Math.max(1, size.height)
    followCamRef.current = aspect < 0.95
    if (!followCamRef.current) {
      const tall = Math.max(0, 1.1 - aspect)
      camBase.current.pos.set(0, 8.6 + tall * 3.2, 12.2 + tall * 5.0)
      camBase.current.look.set(0, 0.3, -1.5 - tall * 1.2)
      // 스크롤 연동 중이면 useFrame이 매 프레임 잡아주므로 초기값만 세팅
      cam.position.copy(camBase.current.pos)
      cam.lookAt(camBase.current.look)
    } else {
      cam.lookAt(S.state.botPos.x, 3.4, S.state.botPos.z - 0.2)
    }
  }, [camera, size, S])

  // 커서 → 지면 타깃 (프로토타입 pointerToGround)
  useEffect(() => {
    if (reduceMotion) return
    const raycaster = new THREE.Raycaster()
    const groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0)
    const ndc = new THREE.Vector2()
    const hitPt = new THREE.Vector3()
    const onMove = (e: PointerEvent) => {
      const r = gl.domElement.getBoundingClientRect()
      ndc.x = ((e.clientX - r.left) / r.width) * 2 - 1
      ndc.y = -((e.clientY - r.top) / r.height) * 2 + 1
      raycaster.setFromCamera(ndc, camera)
      if (raycaster.ray.intersectPlane(groundPlane, hitPt)) {
        hitPt.x = Math.max(-8.5, Math.min(8.5, hitPt.x))
        hitPt.z = Math.max(-7, Math.min(7, hitPt.z))
        S.state.target.copy(hitPt)
        S.state.lastPointer = S.state.time
        if (!pointerActiveRef.current) {
          pointerActiveRef.current = true
          onPointerActive?.()
        }
      }
    }
    window.addEventListener('pointermove', onMove)
    return () => window.removeEventListener('pointermove', onMove)
  }, [camera, gl, reduceMotion, onPointerActive, S])

  useFrame(({ clock, camera: cam }, rawDt) => {
    if (reduceMotion) return
    const st = S.state
    const dt = Math.min(rawDt, 0.05)
    const t = clock.elapsedTime
    st.time = t

    // 해결하는 문제 구간에서 향할 문제 지점 (-1이면 커서 추적)
    const phase = problemRef?.current.phase ?? -1
    const anchor = anchorRef?.current

    // 카드 옆에 설 때는 작게 (미니). 그 외에는 원래 크기로 되돌린다.
    const scaleGoal = anchor?.active ? MINI_SCALE : BASE_SCALE
    const nextScale = S.rig.scale.x + (scaleGoal - S.rig.scale.x) * Math.min(1, dt * 4)
    S.rig.scale.setScalar(nextScale)
    // 그림자도 몸집을 따라간다
    const shadowScale = nextScale / BASE_SCALE
    S.shadow.scale.setScalar(shadowScale)
    // 기능 구간 진행률(0~1). -1이면 경로 주행 아님
    const routeP = routeRef?.current ?? -1
    const onRoute = routeP >= 0

    // 경로선은 기능 구간에서만 서서히 드러난다
    const lineTarget = onRoute ? 1 : 0
    S.plannedMat.opacity += (lineTarget * 0.45 - S.plannedMat.opacity) * 0.08
    S.doneMat.opacity += (lineTarget - S.doneMat.opacity) * 0.08

    if (onRoute) {
      // ── 순찰 경로 주행 — 조향 대신 곡선 위를 미끄러진다 ──
      const rp = Math.min(1, Math.max(0, routeP))
      S.routeCurve.getPointAt(rp, routePos.current)
      st.botPos.lerp(routePos.current, Math.min(1, dt * 5))

      S.routeCurve.getTangentAt(rp, routeTan.current)
      const heading = Math.atan2(routeTan.current.x, routeTan.current.z)
      let dh = heading - S.rig.rotation.y
      while (dh > Math.PI) dh -= 2 * Math.PI
      while (dh < -Math.PI) dh += 2 * Math.PI
      S.rig.rotation.y += dh * Math.min(1, dt * 6)

      // 지나온 경로를 오렌지로 채운다
      S.doneGeo.setDrawRange(0, Math.max(2, Math.round(rp * S.routeSeg)))

    } else if (anchor?.active) {
      // 해결하는 문제 — 지금 카드의 우측 상단에 작게 서 있는다.
      // 화면 좌표를 지면으로 역투영해 목표로 삼으므로 카드 위치와 정확히 맞물린다.
      const rect = gl.domElement.getBoundingClientRect()
      ndc.current.x = ((anchor.x - rect.left) / rect.width) * 2 - 1
      ndc.current.y = -((anchor.y - rect.top) / rect.height) * 2 + 1
      caster.current.setFromCamera(ndc.current, cam)
      if (caster.current.ray.intersectPlane(ground.current, hitPt.current)) {
        st.target.set(hitPt.current.x, 0, hitPt.current.z)
      }
    } else if (phase >= 0 && S.checkpoints[phase]) {
      // (앵커가 없을 때의 대비책) 지도 위 문제 지점으로 이동
      st.target.copy(S.checkpoints[phase].pos)
    } else if (t - st.lastPointer > 2.2) {
      // 커서 없음(대기/터치) → 느린 방랑 순찰
      const a = t * 0.25
      st.target.set(
        Math.cos(a) * 6.2 + Math.cos(a * 2.3) * 1.2,
        0,
        Math.sin(a * 1.1) * 4.8 + Math.sin(a * 1.7) * 1.0,
      )
    }

    // 조향 — 경로 주행 중에는 건너뛴다(곡선이 위치를 직접 결정)
    if (!onRoute) {
      st.tmp.copy(st.target).sub(st.botPos)
      st.tmp.y = 0
      const dist = st.tmp.length()
      const speed = Math.min(9.5, dist * 3.2)
      if (dist > 0.001) {
        st.tmp.normalize().multiplyScalar(speed)
        st.vel.lerp(st.tmp, 0.12)
      } else {
        st.vel.multiplyScalar(0.8)
      }
      st.botPos.addScaledVector(st.vel, dt)
      // 카드 옆에 설 때는 화면 가장자리까지 가야 하므로 순찰 영역보다 넓게 허용
      const bx = anchor?.active ? 16 : 8.5
      const bz = anchor?.active ? 12 : 7
      st.botPos.x = Math.max(-bx, Math.min(bx, st.botPos.x))
      st.botPos.z = Math.max(-bz, Math.min(bz, st.botPos.z))

      if (st.vel.length() > 0.15) {
        const heading = Math.atan2(st.vel.x, st.vel.z)
        let dh = heading - S.rig.rotation.y
        while (dh > Math.PI) dh -= 2 * Math.PI
        while (dh < -Math.PI) dh += 2 * Math.PI
        S.rig.rotation.y += dh * Math.min(1, dt * 8)
      }
    }

    S.rig.position.set(st.botPos.x, Math.sin(t * 3) * 0.03+0.98, st.botPos.z)
    S.shadow.position.set(st.botPos.x, 0.03, st.botPos.z)

    // 액센트 트레일
    if (st.botPos.distanceTo(st.lastDrop) > 0.5) {
      const s = S.trail[st.trailIdx % TRAIL_COUNT]
      st.trailIdx++
      st.lastDrop.copy(st.botPos)
      s.mesh.position.set(st.botPos.x, 0.02, st.botPos.z)
      s.mesh.visible = true
      s.age = 0
    }
    // 색을 중간 톤으로 내렸으므로 불투명도는 다시 낮춘다 — 진한 색은 같은 알파에서
    // 훨씬 무겁게 읽힌다. 대신 잔존 시간은 길게 둬 자취가 이어져 보이게 한다.
    S.trail.forEach((s) => {
      s.age += dt
      const a = Math.max(0, 1 - s.age / 2.4)
      s.mat.opacity = a * 0.6
      s.mesh.scale.setScalar(0.6 + a * 0.6)
      if (a <= 0) s.mesh.visible = false
    })

    // 세로 화면 — 추적 카메라
    if (followCamRef.current) {
      st.camGoal.set(st.botPos.x, 7.7, st.botPos.z + 5.5)
      cam.position.lerp(st.camGoal, 0.09)
      cam.lookAt(st.botPos.x, 3.4, st.botPos.z - 0.2)
    } else if (scrollRef) {
      // 히어로 → 해결하는 문제로 스크롤할수록 카메라가 들리며 단지 전체를 비춘다.
      // 로봇은 그대로 커서를 따라 순찰하므로 두 섹션이 하나의 장면으로 이어진다.
      const p = Math.min(1, Math.max(0, scrollRef.current))
      const b = camBase.current
      camTmp.current.set(b.pos.x, b.pos.y + p * 5.5, b.pos.z + p * 6.5)
      cam.position.lerp(camTmp.current, 0.08)
      lookTmp.current.set(b.look.x, b.look.y - p * 0.3, b.look.z + p * 1.5)
      cam.lookAt(lookTmp.current)
    }

    // 로봇 생동감 (바이저 점멸 · 머리 흔들림)
    animateRoki(S.model, t, 0)

    // 체크포인트 — 기본은 근접 점등, 문제 해결 구간에서는 미해결(빨강)→해결(초록)
    const solved = problemRef?.current.solved ?? -1
    S.checkpoints.forEach((cp, i) => {
      const near = st.botPos.distanceTo(cp.pos) < 1.3
      cp.lit += ((near ? 1 : 0) - cp.lit) * 0.12

      if (onRoute) {
        // 기능 순회 모드 — 대기 지점은 쿨톤 남색(COOL), 로봇이 지나는 곳만 액센트로 점등.
        // 여기서 SOLVED(파랑)를 쓰면 네 지점이 전부 켜진 것처럼 보여 점등 연출이 죽는다.
        cp.solvedAmt += (1 - cp.solvedAmt) * 0.09
        const focus = st.botPos.distanceTo(cp.pos) < 2.2 ? 1 : 0
        cp.lit += (focus - cp.lit) * 0.12
        const col = COOL.clone().lerp(LIT, cp.lit)
        cp.ringMat.color.copy(col)
        cp.dotMat.color.copy(col)
        cp.ring.scale.setScalar(1 + cp.lit * (0.55 + Math.sin(t * 5) * 0.06))
        cp.ringMat.opacity = 0.4 + cp.lit * 0.5
      } else if (solved >= 0) {
        // 문제 서사 모드: i번 문제가 처리됐는지에 따라 색이 넘어간다
        cp.solvedAmt += ((i < solved ? 1 : 0) - cp.solvedAmt) * 0.09
        const col = UNSOLVED.clone().lerp(SOLVED, cp.solvedAmt)
        cp.ringMat.color.copy(col)
        cp.dotMat.color.copy(col)
        // 미해결일수록 크게 경고 펄스, 해결되면 잔잔해진다.
        // 진폭은 낮게 — 빨강은 이 화면에서 유일한 난색이라 같은 세기여도 훨씬 강하게 읽힌다.
        const alarm = (1 - cp.solvedAmt) * (Math.sin(t * 4.2 + i) * 0.5 + 0.5)
        cp.ring.scale.setScalar(1 + alarm * 0.4 + cp.lit * 0.35)
        cp.ringMat.opacity = 0.2 + alarm * 0.22 + cp.solvedAmt * 0.4
      } else {
        const col = COOL.clone().lerp(LIT, cp.lit)
        cp.ringMat.color.copy(col)
        cp.dotMat.color.copy(col)
        cp.ring.scale.setScalar(1 + cp.lit * 0.6 + (near ? Math.sin(t * 6) * 0.05 : 0))
        cp.ringMat.opacity = 0.45 + cp.lit * 0.5
      }
    })

    // 이벤트 핑 펄스
    const k = Math.sin(t * 3.4) * 0.5 + 0.5
    S.evRing.scale.setScalar(1 + k * 0.9)
    S.evRingMat.opacity = 0.32 * (1 - k)
  })

  return (
    <>
      <primitive object={S.root} />
      <hemisphereLight args={[0xffffff, 0x8a8a8a, 0.65]} />
      <directionalLight color={0xffffff} intensity={2.1} position={[-3, 4, 5]} />
      <directionalLight color={0x7dd3fc} intensity={1.4} position={[4, -1, -3]} />
      <directionalLight color={0xdfe6ff} intensity={0.5} position={[3, 2, 4]} />
    </>
  )
}

export type PatrolRobotProps = {
  className?: string
  /** 첫 커서 순찰 시작 시 1회 호출(힌트 숨김용) */
  onPointerActive?: () => void
  /**
   * 0~1 스크롤 진행률. 주면 스크롤에 따라 카메라가 들리며 단지 전체를 비춘다
   * (히어로 → 해결하는 문제 구간을 하나의 장면으로 잇기 위함).
   */
  scrollRef?: MutableRefObject<number>
  /** 문제 해결 서사 — 향할 문제 지점 + 마커 미해결→해결 연출 */
  problemRef?: MutableRefObject<ProblemPhase>
  /** 기능 구간 순찰 경로 진행률 0~1 (-1이면 경로 주행 안 함) */
  routeRef?: MutableRefObject<number>
  /** 화면 좌표 앵커 — 문제 카드 우측 상단에 로봇을 작게 세운다 */
  anchorRef?: MutableRefObject<ScreenAnchor>
  /**
   * 렌더 루프를 돌릴지. 상위가 이미 화면 진입을 추적하고 있으면 그 값을 쓴다.
   * (내부 IntersectionObserver는 절대배치 자식을 관찰하는 터라 한 번 어긋나면 화면이 통째로 빈다)
   */
  active?: boolean
}

export function PatrolRobot({
  className,
  onPointerActive,
  scrollRef,
  problemRef,
  routeRef,
  anchorRef,
  active,
}: PatrolRobotProps) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(true)
  const reduceMotion = usePrefersReducedMotion()

  // 상위가 화면 진입을 알려주면 그걸 쓰고, 아니면 스스로 관찰한다
  useEffect(() => {
    if (active !== undefined) return
    const el = wrapRef.current
    if (!el) return
    const io = new IntersectionObserver((es) => setVisible(es[0].isIntersecting), { threshold: 0.01 })
    io.observe(el)
    return () => io.disconnect()
  }, [active])

  const running = active !== undefined ? active : visible

  return (
    <div ref={wrapRef} className={className} style={{ position: 'absolute', inset: 0 }}>
      <Canvas
        dpr={[1, 2]}
        frameloop={reduceMotion || !running ? 'demand' : 'always'}
        camera={{ fov: 40, near: 0.1, far: 120, position: [0, 8.6, 12.2] }}
        gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}
        onCreated={({ gl, camera }) => {
          gl.setClearColor(0x000000, 0)
          gl.toneMapping = THREE.ACESFilmicToneMapping
          gl.toneMappingExposure = 1.12
          camera.lookAt(0, 0.3, -1.5)
        }}
        aria-label="AI 순찰 로봇 3D 모델"
      >
        <RobotScene
          reduceMotion={reduceMotion}
          onPointerActive={onPointerActive}
          scrollRef={scrollRef}
          problemRef={problemRef}
          routeRef={routeRef}
          anchorRef={anchorRef}
        />
      </Canvas>
    </div>
  )
}
