import * as THREE from 'three'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { ROKI_BASE_YAW, animateRoki, buildRokiCourier } from '../src/components/robot/rokiCourierModel'

/* S15P11E103-296 로키 새 디자인 미리보기 (임시 산출물).
   RobotDiagnosticView.tsx와 카메라·조명·연출을 똑같이 맞춰 둔다. */

const FLOOR_Y = -1.63

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

const host = document.getElementById('stage') as HTMLDivElement
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
renderer.setPixelRatio(Math.min(2, window.devicePixelRatio))
renderer.setClearColor(0x000000, 0)
renderer.toneMapping = THREE.ACESFilmicToneMapping
renderer.toneMappingExposure = 1.0
host.appendChild(renderer.domElement)

const scene = new THREE.Scene()
const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 50)
camera.position.set(0, 2.3, 6.7)
camera.lookAt(0, 0.05, 0)

const pmrem = new THREE.PMREMGenerator(renderer)
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture

const model = buildRokiCourier()
model.root.rotation.y = ROKI_BASE_YAW
scene.add(model.root)

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
scene.add(shadow)

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
scene.add(pool)

scene.add(new THREE.HemisphereLight(0xffffff, 0xd8e2f0, 0.55))
const key = new THREE.DirectionalLight(0xffffff, 1.45)
key.position.set(-3.4, 4.6, 5)
scene.add(key)
const rim = new THREE.DirectionalLight(0x9ec9f5, 0.75)
rim.position.set(4, -0.6, -3)
scene.add(rim)
const fill = new THREE.DirectionalLight(0xeef3ff, 0.4)
fill.position.set(3.4, 2.4, 4)
scene.add(fill)

function resize() {
  const r = host.getBoundingClientRect()
  renderer.setSize(r.width, r.height, false)
  camera.aspect = r.width / Math.max(1, r.height)
  camera.updateProjectionMatrix()
}
resize()
window.addEventListener('resize', resize)

// 드래그로 회전 — 어느 각도에서든 확인할 수 있게
let dragging = false
let lastX = 0
let yawOffset = 0
host.addEventListener('pointerdown', (e) => {
  dragging = true
  lastX = e.clientX
})
window.addEventListener('pointerup', () => {
  dragging = false
})
window.addEventListener('pointermove', (e) => {
  if (!dragging) return
  yawOffset += (e.clientX - lastX) * 0.008
  lastX = e.clientX
})

// 확인용 훅 — 콘솔에서 카메라를 옮겨 부위를 클로즈업할 수 있게 한다
;(window as unknown as Record<string, unknown>).__roki = { camera, renderer, scene, model, freeze: false }

const clock = new THREE.Clock()
function tick() {
  const t = clock.getElapsedTime()
  const dbg = (window as unknown as Record<string, { freeze?: boolean }>).__roki
  if (!dbg?.freeze) {
    animateRoki(model, t)
    model.root.rotation.y += yawOffset
  }
  const pulse = 0.5 + Math.sin(t * 2.4) * 0.14
  ;(pool.material as THREE.MeshBasicMaterial).opacity = pulse
  pool.scale.set(1 + Math.sin(t * 2.4) * 0.04, 0.72, 1)
  renderer.render(scene, camera)
  requestAnimationFrame(tick)
}
tick()
