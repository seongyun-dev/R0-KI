import * as THREE from 'three'
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js'

/* ============================================================
   순찰 로봇 지오메트리/재질 — landing.html Three.js 씬에서 추출.
   랜딩 히어로(PatrolRobot)와 로봇 상세 LIVE DIAGNOSTICS
   (RobotDiagnosticView)가 공유한다. 수치는 프로토타입 그대로.
   ============================================================ */

export type RobotModel = ReturnType<typeof buildRobot>

function glowTexture() {
  const c = document.createElement('canvas')
  c.width = c.height = 128
  const g = c.getContext('2d')!
  const grd = g.createRadialGradient(64, 64, 0, 64, 64, 64)
  grd.addColorStop(0, 'rgba(255,150,90,1)')
  grd.addColorStop(0.35, 'rgba(255,90,38,0.65)')
  grd.addColorStop(1, 'rgba(255,90,38,0)')
  g.fillStyle = grd
  g.fillRect(0, 0, 128, 128)
  return new THREE.CanvasTexture(c)
}

/** 이마(바이저 위)에 얹는 R0-Ki 각인 */
function logoTexture() {
  const c = document.createElement('canvas')
  c.width = 512
  c.height = 160
  const g = c.getContext('2d')!
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  // 캔버스 폭을 최대한 채워야 같은 평면에서도 글자가 크게 보인다
  g.font = 'bold 132px Pretendard, system-ui, sans-serif'
  const target = 470
  const w = g.measureText('R0-Ki').width
  if (w > target) g.font = `bold ${Math.floor((132 * target) / w)}px Pretendard, system-ui, sans-serif`
  g.fillStyle = '#f2f1ef'
  g.fillText('R0-Ki', 256, 84)
  const t = new THREE.CanvasTexture(c)
  t.anisotropy = 4
  return t
}

export function buildRobot() {
  // ---- materials ----
  const bodyMat = new THREE.MeshPhysicalMaterial({ color: 0x0c0c10, metalness: 0.55, roughness: 0.32, clearcoat: 0.9, clearcoatRoughness: 0.28, envMapIntensity: 1.0 })
  const headMat = new THREE.MeshPhysicalMaterial({ color: 0x0a0a0d, metalness: 0.5, roughness: 0.12, clearcoat: 1.0, clearcoatRoughness: 0.08, envMapIntensity: 1.25 })
  const trimMat = new THREE.MeshStandardMaterial({ color: 0x1a1a20, metalness: 0.7, roughness: 0.4, envMapIntensity: 0.8 })
  const visorMat = new THREE.MeshStandardMaterial({ color: 0x120400, emissive: 0xff5a26, emissiveIntensity: 5.0, roughness: 0.35, metalness: 0.2 })
  const lensMat = new THREE.MeshPhysicalMaterial({ color: 0x050506, metalness: 0.2, roughness: 0.05, clearcoat: 1, transmission: 0.1, envMapIntensity: 1.4 })

  const robot = new THREE.Group()
  const head = new THREE.Group()
  robot.add(head)

  // ---- head (helmet dome) ----
  const skull = new THREE.Mesh(new THREE.SphereGeometry(1.18, 72, 72), headMat)
  skull.scale.set(1.0, 1.02, 1.06)
  head.add(skull)
  const face = new THREE.Mesh(new RoundedBoxGeometry(1.62, 1.42, 0.46, 6, 0.55), headMat)
  face.position.set(0, 0.02, 0.9)
  head.add(face)
  head.position.y = 1.28

  // ---- visor (emissive eye slit) + glow sprites ----
  const visor = new THREE.Mesh(new THREE.CapsuleGeometry(0.058, 1.32, 6, 20), visorMat)
  visor.rotation.z = Math.PI / 2
  visor.position.set(0, -0.02, 1.24)
  head.add(visor)
  const glowMat = new THREE.SpriteMaterial({ map: glowTexture(), color: 0xff6a30, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false })
  const glow = new THREE.Sprite(glowMat)
  glow.scale.set(2.1, 0.66, 1)
  glow.position.set(0, -0.02, 1.28)
  head.add(glow)
  const glow2 = new THREE.Sprite(glowMat.clone())
  glow2.scale.set(3.7, 1.3, 1)
  glow2.material.opacity = 0.5
  glow2.position.set(0, -0.02, 1.12)
  head.add(glow2)

  // ---- forehead brand mark ----
  // 이마는 face 박스가 아니라 skull 돔이 앞으로 더 나와 있다(y=0.36에서 돔 앞면 z≈1.20).
  // 돔보다 살짝 앞(1.215)에 두고, 그 지점의 법선 기울기(약 18°)만큼 눕혀 표면에 붙은 것처럼 보이게 한다.
  const logo = new THREE.Mesh(
    new THREE.PlaneGeometry(0.72, 0.225),
    new THREE.MeshBasicMaterial({ map: logoTexture(), transparent: true, depthWrite: false }),
  )
  logo.position.set(0, 0.36, 1.215)
  logo.rotation.x = -0.31
  head.add(logo)

  // ---- side sensor pod ----
  const podArm = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.18, 24), trimMat)
  podArm.rotation.z = Math.PI / 2
  podArm.position.set(1.08, 0.05, 0.15)
  head.add(podArm)
  const pod = new THREE.Mesh(new THREE.SphereGeometry(0.3, 40, 40), headMat)
  pod.position.set(1.28, 0.05, 0.15)
  pod.scale.set(1, 1, 0.85)
  head.add(pod)
  const lens = new THREE.Mesh(new THREE.CircleGeometry(0.16, 32), lensMat)
  lens.position.set(1.42, 0.05, 0.16)
  lens.lookAt(3.2, 0.05, 0.7)
  head.add(lens)
  const lensRing = new THREE.Mesh(new THREE.TorusGeometry(0.17, 0.02, 12, 32), trimMat)
  lensRing.position.copy(lens.position)
  lensRing.quaternion.copy(lens.quaternion)
  head.add(lensRing)

  // head seam + vents
  const seam = new THREE.Mesh(new THREE.TorusGeometry(1.16, 0.012, 10, 80, Math.PI), trimMat)
  seam.rotation.x = Math.PI / 2
  seam.position.y = 0.25
  head.add(seam)
  const ventGeo = new THREE.CapsuleGeometry(0.02, 0.14, 4, 8)
  const vA = new THREE.Mesh(ventGeo, trimMat)
  vA.rotation.x = 0.5
  vA.position.set(-0.18, 0.95, 0.5)
  head.add(vA)
  const vB = new THREE.Mesh(ventGeo, trimMat)
  vB.rotation.x = 0.5
  vB.position.set(0.02, 1.0, 0.45)
  head.add(vB)

  // ---- neck / body ----
  const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.34, 0.4, 0.4, 32), trimMat)
  neck.position.y = 0.42
  robot.add(neck)
  const torso = new THREE.Mesh(new RoundedBoxGeometry(1.7, 1.5, 1.25, 8, 0.5), bodyMat)
  torso.position.y = -0.35
  robot.add(torso)
  const chest = new THREE.Mesh(new THREE.PlaneGeometry(0.7, 0.9), trimMat)
  chest.position.set(0, -0.3, 0.64)
  robot.add(chest)
  const chestDot = new THREE.Mesh(new THREE.CircleGeometry(0.08, 24), visorMat)
  chestDot.position.set(0, 0.05, 0.645)
  robot.add(chestDot)

  // ---- arms / feet ----
  const arm = (sx: number) => {
    const g = new THREE.Group()
    const sh = new THREE.Mesh(new THREE.SphereGeometry(0.42, 32, 32), bodyMat)
    sh.position.set(sx * 0.98, -0.05, 0.05)
    g.add(sh)
    const fore = new THREE.Mesh(new THREE.CapsuleGeometry(0.3, 0.5, 8, 16), bodyMat)
    fore.position.set(sx * 1.02, -0.62, 0.28)
    fore.rotation.z = sx * 0.25
    fore.rotation.x = -0.5
    g.add(fore)
    const hand = new THREE.Mesh(new THREE.SphereGeometry(0.3, 28, 28), headMat)
    hand.position.set(sx * 0.98, -0.98, 0.6)
    g.add(hand)
    return g
  }
  robot.add(arm(-1))
  robot.add(arm(1))
  const foot = (x: number) => {
    const m = new THREE.Mesh(new RoundedBoxGeometry(0.7, 0.5, 1.0, 6, 0.24), bodyMat)
    m.position.set(x, -1.25, 0.28)
    return m
  }
  robot.add(foot(-0.5))
  robot.add(foot(0.5))
  const baseRing = new THREE.Mesh(new THREE.TorusGeometry(0.9, 0.05, 16, 48), trimMat)
  baseRing.rotation.x = Math.PI / 2
  baseRing.position.y = -1.5
  robot.add(baseRing)

  return { robot, head, visor, visorMat, glow, glow2, baseRing }
}

/** 바이저 점멸 + 머리 흔들림 — 두 뷰가 공유하는 "생동감" 애니메이션 */
export function animateRobotLife(model: Pick<RobotModel, 'head' | 'visorMat' | 'glow' | 'glow2'>, t: number) {
  model.visorMat.emissiveIntensity = 4.2 + Math.sin(t * 3) * 1.1
  const gp = 0.85 + Math.sin(t * 3) * 0.15
  model.glow.material.opacity = gp
  model.glow2.material.opacity = gp * 0.5
  model.head.rotation.z = Math.sin(t * 2) * 0.03
}
