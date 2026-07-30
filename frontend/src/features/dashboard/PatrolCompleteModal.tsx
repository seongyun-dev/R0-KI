import type { Patrol } from '../../types/domain'

/* 순찰 완료 알림 — 순찰이 끝나면 대시보드 위에 뜬다.
   완료 사실과 탐지 건수만 알리고, 자세한 내용은 순찰 상세로 넘긴다.
   [확인] 을 누르면 닫히면서 이벤트 이력을 다시 불러온다(호출측이 처리). */

export type PatrolCompleteModalProps = {
  patrol: Patrol
  /** [확인] — 닫고 이벤트 이력 새로고침 */
  onConfirm: () => void
}

export function PatrolCompleteModal({ patrol, onConfirm }: PatrolCompleteModalProps) {
  const robot = patrol.robotName ?? patrol.robotId

  return (
    <div className="modalwrap">
      <div className="backdrop" onClick={onConfirm} />
      <div className="modal glass g3" role="dialog" aria-modal="true" aria-labelledby="pdone-title">
        <div className="mdhead">
          <h2 id="pdone-title">순찰 완료</h2>
          <button type="button" className="mdx" aria-label="닫기" onClick={onConfirm}>
            <svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>

        <p className="mdtext">
          <b>{robot}</b> 순찰이 완료되었습니다.<br />
          {patrol.eventCount > 0 ? (
            <>이벤트 <b>{patrol.eventCount}건</b>이 발생했습니다.</>
          ) : (
            <>발생한 이벤트는 없습니다.</>
          )}
        </p>

        <div className="mdact">
          <button type="button" className="btn btn-p" onClick={onConfirm}>확인</button>
        </div>
      </div>
    </div>
  )
}
