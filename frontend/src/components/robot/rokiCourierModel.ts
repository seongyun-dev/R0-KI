import * as THREE from 'three'
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js'

/* ============================================================
   RO-KI 4륜 배송형 로봇 — 로봇 상세 진단 뷰 전용 (S15P11E103-296).
   흰 박스 셸 + 다크 페이스 패널(픽셀 눈) + 상단 라이다 돔
   + 우측 정비창(모터·배선) + 파란 림 4륜.

   랜딩 히어로가 쓰는 robotModel.ts(휴머노이드)와는 별개다.
   상세페이지만 교체하므로 두 모델은 재질도 공유하지 않는다.

   ⚠️ 실제 GLB 시안이 나오면 buildRokiCourier()만 useGLTF 로더로 갈아끼우면 된다.
   뷰(RobotDiagnosticView)는 아래 RokiCourierModel 필드에만 의존한다.
   ============================================================ */

export type RokiCourierModel = ReturnType<typeof buildRokiCourier>

/** 페이스 패널 눈 색 — R0-Ki 웹 테마 --bot-led 계열 */
const EYE_HEX = '#5ec8ff'
/** 셸 흰색 — 흰 배경에 묻히지 않도록 순백(#fff)보다 살짝 눌러둔다 */
const SHELL = 0xf2f4f7

/* ── 치수 (월드 단위) ──
   셸 -1.33 ~ 1.23 · 라이다 끝 1.74 · 휠 바닥 -1.63 → 전체 높이 ≈ 3.37.
   셸은 한 덩어리로 만들고 뚜껑 분할선은 얕은 홈으로 긋는다. 위·아래를 실제로
   나누면 두 상자의 둥근 모서리가 맞물리는 지점이 잘록해져 버섯처럼 읽힌다. */
const BODY_W = 1.9
const BODY_H = 2.56
const BODY_D = 1.7
const BODY_Y = -0.05
const BODY_R = 0.2
const TOP_Y = BODY_Y + BODY_H / 2
/** 셸 앞면 z (패널·각인을 붙이는 기준면) */
const FRONT_Z = BODY_D / 2
/** 셸 우측면 x (정비창 기준면) */
const SIDE_X = BODY_W / 2
/** 모서리 라운드를 뺀 평면 영역 — 데칼이 둥근 면을 타고 넘지 않게 하는 한계치 */
const FLAT_W = BODY_W - BODY_R * 2
const FLAT_D = BODY_D - BODY_R * 2
/** 뚜껑 분할선 높이 — 페이스 패널 위쪽으로 충분히 띄운다 */
const LID_Y = 0.95

/* 눈 텍스처 해상도 — 패널 폭 기준 한 도트가 화면에서 대여섯 픽셀이 되는 크기 */
const EYE_W = 48
const EYE_H = 24

/**
 * 시안의 도트 눈.
 * 고해상도로 그려 축소하면 링이 군데군데 끊겨 지저분해진다 — 안티에일리어싱된
 * 회색 픽셀이 니어리스트 축소에서 버려지기 때문. 그래서 픽셀 격자에 직접
 * 래스터라이즈한다(원/호는 중심까지의 거리로 판정).
 */
function eyeTexture(closed: boolean) {
  const c = document.createElement('canvas')
  c.width = EYE_W
  c.height = EYE_H
  const g = c.getContext('2d')!
  g.fillStyle = EYE_HEX

  const px = (x: number, y: number) => {
    if (x < 0 || y < 0 || x >= EYE_W || y >= EYE_H) return
    g.fillRect(Math.floor(x), Math.floor(y), 1, 1)
  }

  /** 링/호 — 반지름 r 위의 픽셀만 켠다. from~to 를 주면 그 각도 구간만. */
  const ring = (cx: number, cy: number, r: number, t: number, from?: number, to?: number) => {
    const span = Math.ceil(r + t) + 1
    for (let dy = -span; dy <= span; dy++) {
      for (let dx = -span; dx <= span; dx++) {
        const d = Math.hypot(dx, dy)
        if (Math.abs(d - r) > t) continue
        if (from != null && to != null) {
          const a = Math.atan2(dy, dx)
          if (a < from || a > to) continue
        }
        px(cx + dx, cy + dy)
      }
    }
  }

  /** 채운 원 */
  const disc = (cx: number, cy: number, r: number) => {
    const span = Math.ceil(r) + 1
    for (let dy = -span; dy <= span; dy++) {
      for (let dx = -span; dx <= span; dx++) {
        if (Math.hypot(dx, dy) <= r) px(cx + dx, cy + dy)
      }
    }
  }

  // 좌/우 눈 — 오른쪽이 살짝 작고 낮다(시안의 비대칭 표정).
  // brow* 는 눈썹 호의 각도 구간(캔버스 y는 아래로 자라므로 위쪽이 음수).
  const eyes = [
    { x: 15, y: 12, r: 6.5, browFrom: -2.62, browTo: -1.85 }, // 눈썹이 바깥(좌) 위
    { x: 32, y: 12, r: 5.5, browFrom: -1.29, browTo: -0.52 }, // 눈썹이 바깥(우) 위
  ]

  eyes.forEach((e) => {
    // 눈썹 — 링에서 2.5px 띄운다. 붙으면 눈을 감싼 종처럼 읽힌다
    ring(e.x, e.y, e.r + 2.5, 0.85, e.browFrom, e.browTo)

    if (closed) {
      // 감은 눈 — 아래로 휜 호 하나
      ring(e.x, e.y - 1, e.r, 0.85, 0.55, Math.PI - 0.55)
      return
    }

    ring(e.x, e.y, e.r, 0.85) // 홍채
    disc(e.x, e.y, 1.5) // 동공 — 크면 링 안이 꽉 차 '@' 처럼 읽힌다
    // 하이라이트는 한 점만. 동공 아래로 여러 점을 깔면 세 점이 얼굴처럼 뭉친다
    px(e.x + 2, e.y - 3)
  })

  const tex = new THREE.CanvasTexture(c)
  tex.magFilter = THREE.NearestFilter
  tex.minFilter = THREE.LinearFilter
  tex.generateMipmaps = false
  return tex
}

/** 앞면 하단 RO-KI 각인 */
function wordmarkTexture() {
  const c = document.createElement('canvas')
  c.width = 512
  c.height = 176
  const g = c.getContext('2d')!
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  g.font = 'bold 132px Pretendard, system-ui, sans-serif'
  // 캔버스 폭을 최대한 채워야 같은 평면에서도 글자가 크게 보인다
  const target = 470
  const w = g.measureText('RO-KI').width
  if (w > target) g.font = `bold ${Math.floor((132 * target) / w)}px Pretendard, system-ui, sans-serif`
  g.fillStyle = '#2b2f36'
  g.fillText('RO-KI', 256, 92)
  const t = new THREE.CanvasTexture(c)
  t.anisotropy = 4
  return t
}

/** 휠 정면 — 파란 림 바탕에 다크 멀티스포크. 스포크를 지오메트리로 세우면
    휠 4개 × 10개라 메시가 40개 늘어난다. 텍스처 한 장으로 대신한다. */
function rimTexture() {
  const c = document.createElement('canvas')
  c.width = c.height = 256
  const g = c.getContext('2d')!
  const C = 128

  // 파란 림 — 시안의 채도 높은 코발트
  g.fillStyle = '#1b53da'
  g.beginPath()
  g.arc(C, C, 126, 0, Math.PI * 2)
  g.fill()
  // 림 립 안쪽 그림자
  g.strokeStyle = '#0e2f8c'
  g.lineWidth = 12
  g.beginPath()
  g.arc(C, C, 110, 0, Math.PI * 2)
  g.stroke()

  // 다크 멀티스포크 — 허브에서 림까지 살짝 휘어 나가는 10개
  g.fillStyle = '#1e2229'
  const SPOKES = 10
  for (let i = 0; i < SPOKES; i++) {
    const a = (i / SPOKES) * Math.PI * 2
    const wHub = 0.17
    const wRim = 0.085
    g.beginPath()
    g.moveTo(C + Math.cos(a - wHub) * 32, C + Math.sin(a - wHub) * 32)
    g.lineTo(C + Math.cos(a - wRim + 0.13) * 104, C + Math.sin(a - wRim + 0.13) * 104)
    g.lineTo(C + Math.cos(a + wRim + 0.13) * 104, C + Math.sin(a + wRim + 0.13) * 104)
    g.lineTo(C + Math.cos(a + wHub) * 32, C + Math.sin(a + wHub) * 32)
    g.closePath()
    g.fill()
  }

  // 허브 + 센터 캡
  g.fillStyle = '#1e2229'
  g.beginPath()
  g.arc(C, C, 38, 0, Math.PI * 2)
  g.fill()
  g.fillStyle = '#14171c'
  g.beginPath()
  g.arc(C, C, 15, 0, Math.PI * 2)
  g.fill()

  const t = new THREE.CanvasTexture(c)
  t.anisotropy = 4
  return t
}

/** 정비창 안 배선 — 살짝 늘어진 곡선 튜브 */
function wire(points: THREE.Vector3[], color: number, radius: number) {
  const curve = new THREE.CatmullRomCurve3(points)
  return new THREE.Mesh(
    new THREE.TubeGeometry(curve, 26, radius, 8, false),
    new THREE.MeshStandardMaterial({ color, roughness: 0.6, metalness: 0.1 }),
  )
}

export function buildRokiCourier() {
  // ---- materials ----
  const shellMat = new THREE.MeshPhysicalMaterial({
    color: SHELL,
    metalness: 0.04,
    roughness: 0.4,
    clearcoat: 0.65,
    clearcoatRoughness: 0.3,
    envMapIntensity: 1.0,
  })
  const panelMat = new THREE.MeshPhysicalMaterial({
    color: 0x1e232a,
    metalness: 0.25,
    roughness: 0.16,
    clearcoat: 1.0,
    clearcoatRoughness: 0.06,
    envMapIntensity: 1.2,
  })
  const seamMat = new THREE.MeshBasicMaterial({ color: 0xaeb6c2, transparent: true, opacity: 0.55 })
  const tireMat = new THREE.MeshStandardMaterial({ color: 0x1a1a1d, roughness: 0.88, metalness: 0.04 })
  const rimSideMat = new THREE.MeshStandardMaterial({ color: 0x1b53da, roughness: 0.3, metalness: 0.85 })
  const metalMat = new THREE.MeshStandardMaterial({ color: 0xbcc2ca, roughness: 0.24, metalness: 0.95 })
  const cavityMat = new THREE.MeshStandardMaterial({ color: 0x2b2f36, roughness: 0.8, metalness: 0.1 })

  const root = new THREE.Group()

  // ---- 셸 — 한 덩어리 ----
  const shell = new THREE.Mesh(new RoundedBoxGeometry(BODY_W, BODY_H, BODY_D, 10, BODY_R), shellMat)
  shell.position.y = BODY_Y
  root.add(shell)

  // 뚜껑 분할선 — 보이는 두 면(앞·우)에만 얕게 긋는다
  const seamFront = new THREE.Mesh(new THREE.PlaneGeometry(FLAT_W, 0.018), seamMat)
  seamFront.position.set(0, LID_Y, FRONT_Z + 0.002)
  root.add(seamFront)
  const seamSide = new THREE.Mesh(new THREE.PlaneGeometry(FLAT_D, 0.018), seamMat)
  seamSide.rotation.y = Math.PI / 2
  seamSide.position.set(SIDE_X + 0.002, LID_Y, 0)
  root.add(seamSide)

  // ---- 상단 라이다 — 낮고 넓은 돔. 높으면 굴뚝처럼 읽힌다 ----
  const lidar = new THREE.Group()
  lidar.position.y = TOP_Y
  root.add(lidar)
  const lidarCollar = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.44, 0.07, 44), shellMat)
  lidarCollar.position.y = 0.02
  lidar.add(lidarCollar)
  const lidarBarrel = new THREE.Mesh(new THREE.CylinderGeometry(0.33, 0.34, 0.15, 44), shellMat)
  lidarBarrel.position.y = 0.12
  lidar.add(lidarBarrel)
  const lidarDome = new THREE.Mesh(
    new THREE.SphereGeometry(0.33, 44, 24, 0, Math.PI * 2, 0, Math.PI / 2),
    shellMat,
  )
  lidarDome.position.y = 0.19
  lidar.add(lidarDome)
  // 스캔 노치 — 배럴 옆에 파인 홈. 회전을 눈으로 읽게 해준다
  const notch = new THREE.Mesh(new THREE.BoxGeometry(0.045, 0.14, 0.06), cavityMat)
  notch.position.set(0, 0.14, 0.32)
  lidar.add(notch)

  // ---- 페이스 패널 (다크 스크린) ----
  const facePanel = new THREE.Mesh(new RoundedBoxGeometry(1.44, 0.82, 0.08, 4, 0.1), panelMat)
  facePanel.position.set(0, 0.32, FRONT_Z - 0.012)
  root.add(facePanel)

  // 픽셀 눈 — 패널보다 살짝 앞. toneMapped:false 로 ACES 톤매핑에 눌리지 않게 한다
  const eyeOpenTex = eyeTexture(false)
  const eyeBlinkTex = eyeTexture(true)
  const eyeMat = new THREE.MeshBasicMaterial({
    map: eyeOpenTex,
    transparent: true,
    depthWrite: false,
    toneMapped: false,
  })
  const eyes = new THREE.Mesh(new THREE.PlaneGeometry(1.24, 0.62), eyeMat)
  eyes.position.set(0, 0.35, FRONT_Z + 0.032)
  eyes.renderOrder = 3
  root.add(eyes)

  /* ---- 전면 카메라 렌즈 ----
     시안에는 없는 요소지만, 상세페이지 부위 콜아웃에 '카메라 모듈'이 있어
     지시선이 가리킬 실물이 필요하다. 분할선과 패널 사이에 작게 앉힌다. */
  const lensMat = new THREE.MeshPhysicalMaterial({
    color: 0x0a0e14,
    metalness: 0.3,
    roughness: 0.08,
    clearcoat: 1,
    envMapIntensity: 1.4,
  })
  const lens = new THREE.Mesh(new THREE.CircleGeometry(0.05, 28), lensMat)
  lens.position.set(0, 0.85, FRONT_Z + 0.006)
  root.add(lens)
  const lensRing = new THREE.Mesh(new THREE.TorusGeometry(0.058, 0.012, 10, 28), cavityMat)
  lensRing.position.set(0, 0.85, FRONT_Z + 0.004)
  root.add(lensRing)

  // ---- 앞면 RO-KI 각인 ----
  const wordmark = new THREE.Mesh(
    new THREE.PlaneGeometry(1.22, 0.42),
    new THREE.MeshBasicMaterial({ map: wordmarkTexture(), transparent: true, depthWrite: false }),
  )
  wordmark.position.set(0, -0.36, FRONT_Z + 0.005)
  root.add(wordmark)

  /* ---- 뒷면 — 적재함 도어 + 통풍구 + 후방 LED ----
     360° 회전을 열어 뒀으므로 뒷면이 민무늬 판이면 돌려 볼 이유가 없어진다.
     시안의 언어(얇은 분할선, 흰 셸)를 지키면서 최소한만 얹는다. */
  const BACK_Z = -FRONT_Z

  // 도어 — 살짝 도드라지게 얹으면 모서리가 빛을 받아 윤곽이 드러난다
  const hatch = new THREE.Mesh(new RoundedBoxGeometry(1.42, 1.62, 0.024, 3, 0.09), shellMat)
  hatch.position.set(0, -0.16, BACK_Z - 0.006)
  root.add(hatch)
  // 손잡이
  const handle = new THREE.Mesh(new THREE.CylinderGeometry(0.028, 0.028, 0.34, 16), cavityMat)
  handle.rotation.z = Math.PI / 2
  handle.position.set(0, 0.32, BACK_Z - 0.05)
  root.add(handle)
  // 통풍구 — 도어 위 세 줄
  const ventGeo = new THREE.BoxGeometry(0.52, 0.035, 0.02)
  ;[0.72, 0.8, 0.88].forEach((y) => {
    const vent = new THREE.Mesh(ventGeo, cavityMat)
    vent.position.set(0, y, BACK_Z - 0.004)
    root.add(vent)
  })
  // 후방 LED — 눈과 같은 계열로 켜 둔다
  const tailLight = new THREE.Mesh(
    new THREE.BoxGeometry(0.72, 0.055, 0.022),
    new THREE.MeshStandardMaterial({
      color: 0x0b2233,
      emissive: 0x35acf8,
      emissiveIntensity: 2.4,
      roughness: 0.3,
    }),
  )
  tailLight.position.set(0, -1.08, BACK_Z - 0.005)
  root.add(tailLight)

  // ---- 좌측면 점검 패널 — 우측 정비창과 짝이 되는 닫힌 패널 ----
  const sidePanel = new THREE.Mesh(new RoundedBoxGeometry(0.024, 1.5, 0.6, 3, 0.07), shellMat)
  sidePanel.position.set(-SIDE_X + 0.006, -0.26, 0.1)
  root.add(sidePanel)

  // ---- 우측 정비창 ----
  /* 셸이 한 덩어리 솔리드라 안쪽을 파낼 수 없다(불리언 연산 없음).
     x < SIDE_X 에 둔 부품은 전부 셸 표면에 가린다 — 그래서 창을 밖으로 조금
     띄운 '돌출 하우징'으로 만든다: 흰 테두리 프레임이 서고 그 안쪽으로
     다크 백플레이트 → 모터·배선 → 유리 순으로 쌓인다. */
  const BAY_Z = 0.1
  const BAY_W = 0.56 // 창의 z 방향 폭
  const BAY_H = 1.5
  const BAY_Y = -0.26
  /** 부품이 놓이는 x — 셸 표면(0.95)보다 확실히 바깥이어야 가리지 않는다 */
  const BAY_PART_X = SIDE_X + 0.05
  const BAY_GLASS_X = SIDE_X + 0.15

  const bay = new THREE.Group()
  root.add(bay)

  // 다크 백플레이트 — 창 안쪽 벽
  const back = new THREE.Mesh(new RoundedBoxGeometry(0.03, BAY_H, BAY_W, 3, 0.04), cavityMat)
  back.position.set(SIDE_X + 0.025, BAY_Y, BAY_Z)
  bay.add(back)

  // 휠 모터 — 창 아래쪽 가로 실린더 + 샤프트
  const motor = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.1, 0.3, 26), metalMat)
  motor.rotation.x = Math.PI / 2
  motor.position.set(BAY_PART_X, -0.7, BAY_Z - 0.04)
  bay.add(motor)
  const motorShaft = new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.055, 0.14, 20), metalMat)
  motorShaft.rotation.x = Math.PI / 2
  motorShaft.position.set(BAY_PART_X, -0.7, BAY_Z + 0.19)
  bay.add(motorShaft)
  const motorBand = new THREE.Mesh(new THREE.TorusGeometry(0.104, 0.016, 10, 30), cavityMat)
  motorBand.rotation.y = Math.PI / 2
  motorBand.rotation.z = Math.PI / 2
  motorBand.position.copy(motor.position)
  bay.add(motorBand)

  // 배선 — 위 커넥터에서 모터로 내려오는 주황/회색 가닥
  bay.add(
    wire(
      [
        new THREE.Vector3(BAY_PART_X, 0.34, BAY_Z - 0.13),
        new THREE.Vector3(BAY_PART_X, 0.0, BAY_Z + 0.02),
        new THREE.Vector3(BAY_PART_X, -0.34, BAY_Z - 0.11),
        new THREE.Vector3(BAY_PART_X, -0.6, BAY_Z - 0.03),
      ],
      0xd2743c,
      0.026,
    ),
  )
  bay.add(
    wire(
      [
        new THREE.Vector3(BAY_PART_X, 0.32, BAY_Z + 0.15),
        new THREE.Vector3(BAY_PART_X, -0.06, BAY_Z + 0.21),
        new THREE.Vector3(BAY_PART_X, -0.42, BAY_Z + 0.13),
        new THREE.Vector3(BAY_PART_X, -0.64, BAY_Z + 0.15),
      ],
      0x939aa4,
      0.023,
    ),
  )
  // 창 상단 커넥터 블록
  const connector = new THREE.Mesh(new THREE.BoxGeometry(0.09, 0.22, 0.34), metalMat)
  connector.position.set(BAY_PART_X, 0.46, BAY_Z)
  bay.add(connector)

  // 유리 — transmission 은 무거워서 얇은 반투명 평면으로 대신한다
  const glass = new THREE.Mesh(
    new THREE.PlaneGeometry(BAY_W, BAY_H),
    new THREE.MeshPhysicalMaterial({
      color: 0xe4edf8,
      transparent: true,
      opacity: 0.14,
      roughness: 0.05,
      metalness: 0,
      clearcoat: 1,
      side: THREE.DoubleSide,
    }),
  )
  glass.rotation.y = Math.PI / 2
  glass.position.set(BAY_GLASS_X, BAY_Y, BAY_Z)
  bay.add(glass)

  // 흰 테두리 프레임 — 창을 감싸 '움푹 들어간 점검창'으로 읽히게 한다
  const FRAME_T = 0.07
  const frameX = SIDE_X + 0.09
  const frameDepth = 0.2
  const hBar = new THREE.BoxGeometry(frameDepth, FRAME_T, BAY_W + FRAME_T * 2)
  const vBar = new THREE.BoxGeometry(frameDepth, BAY_H + FRAME_T * 2, FRAME_T)
  ;[BAY_H / 2 + FRAME_T / 2, -BAY_H / 2 - FRAME_T / 2].forEach((dy) => {
    const bar = new THREE.Mesh(hBar, shellMat)
    bar.position.set(frameX, BAY_Y + dy, BAY_Z)
    bay.add(bar)
  })
  ;[BAY_W / 2 + FRAME_T / 2, -BAY_W / 2 - FRAME_T / 2].forEach((dz) => {
    const bar = new THREE.Mesh(vBar, shellMat)
    bar.position.set(frameX, BAY_Y, BAY_Z + dz)
    bay.add(bar)
  })

  // ---- 휠 4개 + 짧은 액슬 ----
  /* 타이어 단면(tube)을 두껍게 잡으면 도넛처럼 보인다 — 시안처럼 큼직한
     블루 림 + 얇은 사이드월 비율로 간다. */
  const rimTex = rimTexture()
  const TIRE_R = 0.38 // 토러스 중심선 반지름 = 림 반지름
  const TIRE_T = 0.13 // 타이어 단면 반지름
  const WHEEL_X = 1.08
  const WHEEL_Z = 0.62
  const WHEEL_Y = -1.12
  const wheelAt = (sx: number, z: number) => {
    const g = new THREE.Group()
    g.position.set(sx * WHEEL_X, WHEEL_Y, z)

    const tire = new THREE.Mesh(new THREE.TorusGeometry(TIRE_R, TIRE_T, 20, 48), tireMat)
    tire.rotation.y = Math.PI / 2 // 토러스 축을 X로 눕힌다
    g.add(tire)

    // 배럴 — 토러스 구멍을 메워 타이어 안쪽이 비지 않게 한다
    const barrel = new THREE.Mesh(
      new THREE.CylinderGeometry(TIRE_R, TIRE_R, TIRE_T * 2, 44),
      rimSideMat,
    )
    barrel.rotation.z = Math.PI / 2
    g.add(barrel)

    /* 스포크 면 — 양쪽에 붙인다. 바깥쪽만 붙이면 3/4 뷰에서 안쪽을 보게 되는
       휠(좌측)이 민무늬 파란 원판으로 남는다.
       metalness 를 높이면 환경 반사가 어두운 스포크를 덮어 하얗게 날아간다. */
    const faceMat = new THREE.MeshStandardMaterial({
      map: rimTex,
      roughness: 0.45,
      metalness: 0.3,
      envMapIntensity: 0.55,
    })
    ;[1, -1].forEach((side) => {
      const face = new THREE.Mesh(new THREE.CircleGeometry(TIRE_R, 48), faceMat)
      face.position.x = side * (TIRE_T + 0.002)
      face.rotation.y = side * (Math.PI / 2)
      g.add(face)
    })

    return g
  }
  const wheels = [wheelAt(-1, WHEEL_Z), wheelAt(1, WHEEL_Z), wheelAt(-1, -WHEEL_Z), wheelAt(1, -WHEEL_Z)]
  wheels.forEach((w) => root.add(w))

  // 액슬 — 셸에서 휠까지 잇는 짧은 축. 없으면 휠이 떠 있는 것처럼 보인다
  const axleGeo = new THREE.CylinderGeometry(0.09, 0.09, 0.26, 20)
  ;[-1, 1].forEach((sx) => {
    ;[WHEEL_Z, -WHEEL_Z].forEach((z) => {
      const axle = new THREE.Mesh(axleGeo, cavityMat)
      axle.rotation.z = Math.PI / 2
      axle.position.set(sx * (WHEEL_X - 0.1), WHEEL_Y, z)
      root.add(axle)
    })
  })

  return { root, lidar, eyes, eyeMat, eyeOpenTex, eyeBlinkTex, wheels, facePanel, shellMat }
}

/** 진단 뷰 기본 자세 — 앞면은 살짝 왼쪽, 우측 정비창이 보이도록 튼 3/4 뷰(시안 구도) */
export const ROKI_BASE_YAW = -0.45

/**
 * 부위 콜아웃이 가리킬 지점 — 모델 로컬 좌표.
 * 순서는 로봇 상세의 parts(카메라/라이다/휠모터/구동부)와 1:1 대응한다.
 * normal 은 그 부위가 바라보는 방향 — 카메라 반대편으로 돌아가면 지시선을 흐리는 데 쓴다.
 * (로봇이 회전하므로 매 프레임 root.matrixWorld 를 먹여 월드 좌표로 옮겨야 한다)
 */
export const ROKI_PART_ANCHORS = [
  { key: 'cam', point: [0, 0.85, 0.92], normal: [0, 0, 1] },
  { key: 'lidar', point: [0, 1.6, 0.22], normal: [0, 0.72, 0.7] },
  { key: 'motor', point: [1.05, -0.7, 0.1], normal: [1, 0, 0] },
  { key: 'drive', point: [-1.08, -1.12, 0.62], normal: [-0.8, -0.2, 0.56] },
] as const

/** 생동감 — 부유 · 라이다 스캔 회전 · 눈 깜빡임. yaw 는 뷰가 소유한다(드래그/스크롤 회전) */
export function animateRoki(model: RokiCourierModel, t: number, yaw: number) {
  model.root.position.y = Math.sin(t * 1.5) * 0.022
  model.root.rotation.y = yaw

  // 라이다는 실제 스캐너처럼 한 방향으로 계속 돈다
  model.lidar.rotation.y = t * 0.9

  // 깜빡임 — 4.6초마다 0.13초. 텍스처를 갈아끼워 도트 감을 유지한다
  const blinking = t % 4.6 > 4.47
  const wanted = blinking ? model.eyeBlinkTex : model.eyeOpenTex
  if (model.eyeMat.map !== wanted) {
    model.eyeMat.map = wanted
    model.eyeMat.needsUpdate = true
  }
  model.eyeMat.opacity = 0.93 + Math.sin(t * 2.6) * 0.07
}
