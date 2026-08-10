import * as THREE from 'three'

/* 순찰 씬 공용 텍스처 — 히어로(PatrolRobot)와 순찰 여정(PatrolJourneyScene) 공유.
   수치는 landing.html 프로토타입 그대로. */

/** 단지 바닥 그리드 — 연한 하늘 바닥 + 흰 선 (S15P11E103-276)
 *
 * 선을 흰색으로 두려면 바닥이 선보다 어두워야 한다. 그래서 바닥에 아주 연한 하늘색을
 * 깔고 그 위에 순백 선을 얹는다. 페이지 배경도 같은 톤의 연한 하늘 그라데이션이라
 * 캔버스 영역만 따로 뜨지 않는다(GROUND_TINT 를 그 그라데이션 중간값에 맞춰둔다).
 */
export const GROUND_TINT = '#E1EDFA'

export function gridTexture() {
  const s = 1024
  const c = document.createElement('canvas')
  c.width = c.height = s
  const g = c.getContext('2d')!
  g.fillStyle = GROUND_TINT
  g.fillRect(0, 0, s, s)
  const step = s / 16

  const line = (p: number) => {
    g.beginPath(); g.moveTo(p, 0); g.lineTo(p, s); g.stroke()
    g.beginPath(); g.moveTo(0, p); g.lineTo(s, p); g.stroke()
  }

  // 보조선 — 사실상 순백
  g.strokeStyle = 'rgba(255,255,255,0.95)'
  g.lineWidth = 2
  for (let i = 0; i <= 16; i++) line(i * step)

  // 주선 — 순백, 조금 더 굵게. 4칸마다 구획을 잡는다
  g.strokeStyle = '#FFFFFF'
  g.lineWidth = 4
  for (let i = 0; i <= 16; i += 4) line(i * step)

  const t = new THREE.CanvasTexture(c)
  t.wrapS = t.wrapT = THREE.RepeatWrapping
  t.repeat.set(7, 7)
  t.anisotropy = 4
  return t
}

/** 로봇 접지 그림자 */
export function shadowTexture() {
  const c = document.createElement('canvas')
  c.width = c.height = 128
  const g = c.getContext('2d')!
  const rd = g.createRadialGradient(64, 64, 0, 64, 64, 64)
  rd.addColorStop(0, 'rgba(20,18,15,0.5)')
  rd.addColorStop(0.6, 'rgba(20,18,15,0.16)')
  rd.addColorStop(1, 'rgba(20,18,15,0)')
  g.fillStyle = rd
  g.fillRect(0, 0, 128, 128)
  return new THREE.CanvasTexture(c)
}
