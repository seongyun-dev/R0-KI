/* 순찰 종료 확인 — 대시보드의 순찰중 로봇을 눌렀을 때 표시한다.
   API 성공은 정지 명령 접수이며, 실제 순찰 종료는 로봇의 STOP_PATROL 성공 ACK 이후 확정된다. */

export type PatrolStopModalProps = {
  robot: { name: string; battery?: number | null }
  stopping: boolean
  error?: string
  onCancel: () => void
  onConfirm: () => void
}

export function PatrolStopModal({
  robot,
  stopping,
  error,
  onCancel,
  onConfirm,
}: PatrolStopModalProps) {
  return (
    <div className="modalwrap">
      {/* 요청 결과를 확인하기 전 모달이 닫혀 종료 여부를 놓치지 않도록 요청 중에는 닫기를 막는다. */}
      <div className="backdrop" onClick={stopping ? undefined : onCancel} />
      <div className="modal glass g3" role="dialog" aria-modal="true" aria-labelledby="pstop-title">
        <div className="mdhead">
          <h2 id="pstop-title">순찰 종료</h2>
          <button type="button" className="mdx" aria-label="닫기" onClick={onCancel} disabled={stopping}>
            <svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>

        <p className="mdtext">
          <b>{robot.name}</b> 로봇의 현재 순찰을 종료합니다.
        </p>
        <p className="psmeta">
          <i className="d" />
          배터리 {robot.battery != null ? `${robot.battery}%` : '확인 불가'}
        </p>
        <p className="pswarn">로봇에 정지 명령을 전송합니다. 실제 정지까지 잠시 기다려 주세요.</p>

        {error && <p className="pserr" role="alert">{error}</p>}

        <div className="mdact psact">
          <button type="button" className="btn btn-s" onClick={onCancel} disabled={stopping}>취소</button>
          <button type="button" className="btn btn-p" onClick={onConfirm} disabled={stopping}>
            {stopping ? '종료 요청 중…' : '순찰 종료'}
          </button>
        </div>
      </div>
    </div>
  )
}
