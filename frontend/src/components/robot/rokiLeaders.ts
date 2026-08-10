import * as THREE from 'three'
import { ROKI_PART_ANCHORS } from './rokiCourierModel'

/* 부위 콜아웃 지시선 계산 (S15P11E103-296).
   로봇이 드래그로 회전하므로 지시선 끝점을 CSS 고정 좌표로 둘 수 없다 —
   부위의 3D 좌표를 매 프레임 화면으로 투영해서 잇는다.

   3D 뷰(RobotDiagnosticView)와 상세페이지(RobotDetail)가 나눠 쓰는 계산이라
   여기 모아 둔다. 미리보기 하니스도 같은 함수를 쓴다. */

/** 부위 앵커를 캔버스 정규 좌표(0~1)로 투영한 결과 */
export type ProjectedAnchor = {
  key: string
  /** 캔버스 좌상단 기준 0~1 */
  x: number
  y: number
  /** 부위가 카메라를 향하는 정도 0~1 — 뒤로 돌아가면 0에 가까워진다 */
  facing: number
}

/** getBoundingClientRect 결과를 그대로 넣을 수 있는 최소 형태 */
export type LeaderRect = { left: number; top: number; width: number; height: number }

export type LeaderLine = {
  x1: number
  y1: number
  x2: number
  y2: number
  opacity: number
}

// 매 프레임 새로 만들면 GC가 튄다
const tmpPoint = new THREE.Vector3()
const tmpNormal = new THREE.Vector3()
const tmpView = new THREE.Vector3()

/** 로봇의 각 부위를 카메라로 투영한다. root 는 회전하는 모델 그룹. */
export function projectPartAnchors(root: THREE.Object3D, camera: THREE.Camera): ProjectedAnchor[] {
  root.updateMatrixWorld()
  camera.getWorldDirection(tmpView)

  return ROKI_PART_ANCHORS.map((a) => {
    tmpPoint.set(a.point[0], a.point[1], a.point[2]).applyMatrix4(root.matrixWorld).project(camera)
    // 법선은 회전만 먹인다(이동 성분 제외)
    tmpNormal
      .set(a.normal[0], a.normal[1], a.normal[2])
      .applyQuaternion(root.quaternion)
      .normalize()
    // 시선과 반대로 향할수록(= dot이 음수) 정면
    const facing = THREE.MathUtils.clamp(-tmpNormal.dot(tmpView), 0, 1)

    return { key: a.key, x: (tmpPoint.x + 1) / 2, y: (1 - tmpPoint.y) / 2, facing }
  })
}

/**
 * 콜아웃 박스에서 부위까지 이을 선분을 프레임 기준 px로 낸다.
 * .rd-3d 캔버스는 프레임보다 크게 깔려 있어 두 사각형의 차이를 반드시 반영해야 한다.
 */
export function layoutLeader(
  anchor: ProjectedAnchor,
  frame: LeaderRect,
  canvas: LeaderRect,
  box: LeaderRect,
): LeaderLine {
  const tx = canvas.left - frame.left + anchor.x * canvas.width
  const ty = canvas.top - frame.top + anchor.y * canvas.height

  const bx = box.left - frame.left
  const by = box.top - frame.top
  // 부위가 있는 쪽 변의 중점에서 선을 뽑는다
  const fromRight = tx >= bx + box.width / 2

  return {
    x1: fromRight ? bx + box.width : bx,
    y1: by + box.height / 2,
    x2: tx,
    y2: ty,
    // 부위가 뒤로 돌아가면 흐려진다 — 안 보이는 곳을 또렷하게 가리키면 거짓말이 된다
    opacity: 0.22 + anchor.facing * 0.62,
  }
}
