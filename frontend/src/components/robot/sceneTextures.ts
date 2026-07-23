import * as THREE from 'three'

/* 순찰 씬 공용 텍스처 — 히어로(PatrolRobot)와 순찰 여정(PatrolJourneyScene) 공유.
   수치는 landing.html 프로토타입 그대로. */

/** 단지 바닥 그리드 (블루프린트 감각) */
export function gridTexture() {
  const s = 1024
  const c = document.createElement('canvas')
  c.width = c.height = s
  const g = c.getContext('2d')!
  g.fillStyle = '#f3f1ee'
  g.fillRect(0, 0, s, s)
  const step = s / 16
  g.strokeStyle = 'rgba(24,30,48,0.06)'
  g.lineWidth = 2
  for (let i = 0; i <= 16; i++) {
    const p = i * step
    g.beginPath(); g.moveTo(p, 0); g.lineTo(p, s); g.stroke()
    g.beginPath(); g.moveTo(0, p); g.lineTo(s, p); g.stroke()
  }
  g.strokeStyle = 'rgba(24,30,48,0.11)'
  g.lineWidth = 3
  for (let i = 0; i <= 16; i += 4) {
    const p = i * step
    g.beginPath(); g.moveTo(p, 0); g.lineTo(p, s); g.stroke()
    g.beginPath(); g.moveTo(0, p); g.lineTo(s, p); g.stroke()
  }
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
