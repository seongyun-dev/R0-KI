import { R0KiModal } from '../../components/layout/R0KiModal'

/* 회원가입 완료 모달 (1u+) — 계정 등록 직후.
   여기서 끝내고 나가도 계정은 이미 만들어져 있다. 다만 로봇·지도가 없으면
   관제 화면이 비어 있으므로, 다음에 로그인해도 온보딩으로 다시 돌아온다는 걸 알려준다. */

export type SignupDoneModalProps = {
  open: boolean
  /** [로봇 등록하러 가기] — 온보딩 계속 */
  onContinue: () => void
  /** [나중에 하기] — 로그인 화면으로 */
  onLater: () => void
}

export function SignupDoneModal({ open, onContinue, onLater }: SignupDoneModalProps) {
  return (
    <R0KiModal open={open} onClose={onLater} title="회원가입 완료">
      <p className="mdtext">
        계정이 등록되었습니다.<br />
        관제를 시작하려면 <b>순찰 로봇과 단지 지도</b>를 등록해야 합니다.
      </p>

      <div className="au-note">
        <svg viewBox="0 0 24 24"><path d="M12 8h.01M11 12h1v5h1" /><circle cx="12" cy="12" r="9" /></svg>
        <span>지금 그만두어도 <b>다음 로그인 때 이어서</b> 진행할 수 있습니다.</span>
      </div>

      <div className="mdact">
        <button type="button" className="btn btn-s" onClick={onLater}>
          나중에 하기
        </button>
        <button type="button" className="btn btn-p btn-add" onClick={onContinue}>
          로봇 등록하러 가기
          <svg viewBox="0 0 24 24"><path d="M5 12h13M12 5l7 7-7 7" /></svg>
        </button>
      </div>
    </R0KiModal>
  )
}
