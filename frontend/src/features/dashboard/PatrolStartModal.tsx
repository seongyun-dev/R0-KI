/* 순찰 시작 확인 — 대시보드 로봇 목록에서 '대기' 로봇을 누르면 뜬다.
   순찰은 로봇이 실제로 움직이는 동작이고 시작 뒤 되돌리는 버튼이 없으므로,
   누르기 전에 대상 로봇과 배터리를 한 번 더 보여주고 확인을 받는다.
   경비원(고령 사용자) 기준이라 본문·버튼 글자를 크게 두고, 상태는 색이 아니라 문구로 알린다. */

export type PatrolStartModalProps = {
  robot: { name: string; battery?: number | null }
  /** 시작 요청 진행 중 — 중복 요청을 막고 버튼 문구를 바꾼다 */
  starting: boolean
  /** 시작 실패 사유 — 모달을 닫지 않고 그 자리에 남긴다 */
  error?: string
  onCancel: () => void
  onConfirm: () => void
}

// 로봇 칩의 빨간 게이지 기준(25%)과 같은 값 — 같은 화면에서 기준이 어긋나면 안 된다
const LOW_BATTERY = 25

export function PatrolStartModal({
  robot,
  starting,
  error,
  onCancel,
  onConfirm,
}: PatrolStartModalProps) {
  const battery = robot.battery
  const isLow = battery != null && battery <= LOW_BATTERY

  return (
    <div className="modalwrap">
      {/* 요청 중에는 바깥을 눌러도 닫히지 않는다 — 응답 전에 사라지면 시작 여부를 알 수 없다 */}
      <div className="backdrop" onClick={starting ? undefined : onCancel} />
      <div className="modal glass g3" role="dialog" aria-modal="true" aria-labelledby="pstart-title">
        <div className="mdhead">
          <h2 id="pstart-title">순찰 시작</h2>
          <button
            type="button"
            className="mdx"
            aria-label="닫기"
            onClick={onCancel}
            disabled={starting}
          >
            <svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>

        <p className="mdtext">
          <b>{robot.name}</b> 로봇이 지금 순찰을 시작합니다.
        </p>

        <p className="psmeta">
          <i className="d" />
          배터리 {battery != null ? `${battery}%` : '확인 불가'}
        </p>

        {isLow && (
          <p className="pswarn">
            배터리가 얼마 남지 않았습니다. 순찰 도중 로봇이 멈출 수 있습니다.
          </p>
        )}

        {error && <p className="pserr" role="alert">{error}</p>}

        <div className="mdact psact">
          <button type="button" className="btn btn-s" onClick={onCancel} disabled={starting}>
            취소
          </button>
          <button type="button" className="btn btn-p" onClick={onConfirm} disabled={starting}>
            {starting ? '시작 중…' : '순찰 시작'}
          </button>
        </div>
      </div>
    </div>
  )
}
