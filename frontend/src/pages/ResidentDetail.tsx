import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { R0KiShell } from '../components/layout/R0KiShell'
import {
  eventTypeLabel,
  formatDateTimeLabel,
  notificationStatusLabel,
  useAddResidentVehicle,
  useChangeResidentNotification,
  useDeleteResidentVehicle,
  useResident,
  useUpdateResident,
} from '../features/residents/useResidents'

/* R0-Ki 입주민 상세 — 알림/이벤트 상세와 같은 2단 유리 레이아웃.
   좌: 등록 차량 + 알림 이력 / 우: 기본 정보 수정 + 알림 수신 토글.

   알림 수신을 끄면 불법주차가 잡혀도 SMS 가 안 나가므로(백엔드
   NotificationService.requestIllegalParkingNotification) 토글 옆에 그 영향을 적어 둔다. */

const PHONE_PATTERN = /^[0-9-]+$/

function StatusChip({ status }: { status: string }) {
  const label = notificationStatusLabel(status)
  if (label === '발송실패') return <span className="st u"><i />발송실패</span>
  return (
    <span className="st">
      <i style={{ background: label === '발송완료' ? 'var(--offline)' : 'var(--charge)' }} />
      {label}
    </span>
  )
}

export default function ResidentDetail() {
  const { id } = useParams()
  const { data: resident, isLoading, error, refetch } = useResident(id)

  const updateResident = useUpdateResident()
  const changeNotification = useChangeResidentNotification()
  const addVehicle = useAddResidentVehicle()
  const deleteVehicle = useDeleteResidentVehicle()

  const toastTimer = useRef<number>()
  const [toast, setToast] = useState<string>()
  const [actionError, setActionError] = useState<string>()

  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({
    name: '',
    phoneNumber: '',
    buildingNumber: '',
    unitNumber: '',
  })
  // 차량은 번호만 입력받는다 — disabledVehicle 은 이 화면에서 다루지 않으므로 항상 false 로 보낸다
  const [newPlate, setNewPlate] = useState('')

  useEffect(() => () => window.clearTimeout(toastTimer.current), [])

  const showToast = (message: string) => {
    setToast(message)
    window.clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => setToast(undefined), 2000)
  }

  const startEditing = () => {
    if (!resident) return
    setForm({
      name: resident.name,
      phoneNumber: resident.phoneNumber,
      buildingNumber: resident.buildingNumber,
      unitNumber: resident.unitNumber,
    })
    setActionError(undefined)
    setEditing(true)
  }

  const runAction = async (action: () => Promise<unknown>, successMessage: string) => {
    setActionError(undefined)
    try {
      await action()
      showToast(successMessage)
      refetch()
      return true
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : '요청을 처리하지 못했습니다.')
      return false
    }
  }

  const onSave = async () => {
    if (!id) return
    const name = form.name.trim()
    const phoneNumber = form.phoneNumber.trim()
    const buildingNumber = form.buildingNumber.trim()
    const unitNumber = form.unitNumber.trim()

    if (!name || !phoneNumber || !buildingNumber || !unitNumber) {
      setActionError('이름·연락처·동·호수는 모두 필수입니다.')
      return
    }
    if (!PHONE_PATTERN.test(phoneNumber)) {
      setActionError('연락처는 숫자와 하이픈만 입력할 수 있습니다.')
      return
    }

    const ok = await runAction(
      () =>
        updateResident.mutateAsync({
          residentId: id,
          request: { name, phoneNumber, buildingNumber, unitNumber },
        }),
      '입주민 정보가 수정되었습니다',
    )
    if (ok) setEditing(false)
  }

  const onToggleNotification = async () => {
    if (!id || !resident) return
    await runAction(
      () =>
        changeNotification.mutateAsync({
          residentId: id,
          request: { notificationEnabled: !resident.notificationEnabled },
        }),
      resident.notificationEnabled ? '알림 수신을 껐습니다' : '알림 수신을 켰습니다',
    )
  }

  const onAddVehicle = async () => {
    if (!id) return
    const licensePlate = newPlate.trim()
    if (!licensePlate) {
      setActionError('차량 번호를 입력해 주세요.')
      return
    }
    const ok = await runAction(
      () =>
        addVehicle.mutateAsync({
          residentId: id,
          request: { licensePlate, disabledVehicle: false },
        }),
      '차량이 등록되었습니다',
    )
    if (ok) setNewPlate('')
  }

  const onDeleteVehicle = async (vehicleId: number, licensePlate: string) => {
    if (!id) return
    if (!window.confirm(`${licensePlate} 차량을 삭제할까요?`)) return
    await runAction(
      () => deleteVehicle.mutateAsync({ residentId: id, vehicleId }),
      '차량이 삭제되었습니다',
    )
  }

  const busy =
    updateResident.isPending ||
    changeNotification.isPending ||
    addVehicle.isPending ||
    deleteVehicle.isPending

  return (
    <R0KiShell active="residents">
      <div className="pcol">
        <div className="pagehead">
          <div>
            <div className="crumb">
              <Link to="/app">대시보드</Link><i>›</i>
              <Link to="/app/residents">입주민 관리</Link><i>›</i>
              <b>{resident ? `${resident.buildingNumber}동 ${resident.unitNumber}호` : id}</b>
            </div>
            <div className="ptitle row">
              입주민 상세
              {resident && (
                <>
                  <span className="sub">{resident.name}</span>
                  {resident.notificationEnabled ? (
                    <span className="st">
                      <i style={{ background: 'var(--offline)' }} />
                      알림 수신
                    </span>
                  ) : (
                    <span className="st u"><i />알림 차단</span>
                  )}
                </>
              )}
            </div>
          </div>
        </div>

        {error ? (
          <div className="glass g2 aisum">
            <div className="zh2"><span className="zn">입주민을 불러오지 못했습니다</span></div>
            <button type="button" className="btn btn-s" onClick={refetch}>다시 시도</button>
          </div>
        ) : !resident ? (
          <div className="glass g2 aisum">
            <div className="zh2">
              <span className="zn">
                {isLoading ? '불러오는 중…' : `입주민(${id})을 찾을 수 없습니다`}
              </span>
            </div>
            {!isLoading && <Link to="/app/residents" className="btn btn-s">목록으로</Link>}
          </div>
        ) : (
          <div className="egrid">
            {/* 등록 차량 + 알림 이력 */}
            <div className="glass g2 dcol" style={{ padding: 'var(--s5)' }}>
              <div className="zh2">
                <span className="zn">등록 차량</span>
                <span className="zsub">
                  불법주차 안내 문자는 등록된 차량에만 발송됩니다
                </span>
              </div>

              {resident.vehicles.length === 0 ? (
                <div className="empty">
                  <svg viewBox="0 0 24 24">
                    <path d="M5 16h14M6.5 16V9.5l1.8-3.5h7.4l1.8 3.5V16" />
                    <circle cx="8" cy="18" r="1.6" /><circle cx="16" cy="18" r="1.6" />
                  </svg>
                  <span>등록된 차량이 없습니다</span>
                </div>
              ) : (
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>차량 번호</th>
                      <th>장애인 차량</th>
                      <th className="r" />
                    </tr>
                  </thead>
                  <tbody>
                    {resident.vehicles.map((vehicle) => (
                      <tr key={vehicle.vehicleId}>
                        <td className="num">{vehicle.licensePlate}</td>
                        <td>{vehicle.disabledVehicle ? '예' : <span className="dash">—</span>}</td>
                        <td className="r">
                          <button
                            type="button"
                            className="btn btn-s"
                            disabled={busy}
                            onClick={() =>
                              onDeleteVehicle(vehicle.vehicleId, vehicle.licensePlate)
                            }
                          >
                            삭제
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 'var(--s2)',
                  marginTop: 'var(--s3)',
                }}
              >
                {/* .au-in 은 width:100% 라 그냥 두면 입력칸이 행을 다 먹고 옆 버튼이 찌그러진다.
                    입력칸만 늘어나게 하고(flex:1+min-width:0) 나머지는 제 너비를 지킨다. */}
                <input
                  className="au-in num"
                  value={newPlate}
                  onChange={(event) => setNewPlate(event.target.value)}
                  placeholder="예: 12가3456"
                  aria-label="추가할 차량 번호"
                  autoComplete="off"
                  style={{ flex: '1 1 auto', minWidth: 0 }}
                />
                <button
                  type="button"
                  className="btn btn-s btn-add"
                  onClick={onAddVehicle}
                  disabled={busy}
                  style={{ flex: 'none', whiteSpace: 'nowrap' }}
                >
                  <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>
                  차량 추가
                </button>
              </div>

              <div className="zh2" style={{ marginTop: 'var(--s5)' }}>
                <span className="zn">알림 이력</span>
                <span className="zsub">
                  최근 {resident.recentNotifications.length}건 · 전체 {resident.notificationCount}건
                </span>
              </div>

              {resident.recentNotifications.length === 0 ? (
                <div className="empty">
                  <svg viewBox="0 0 24 24">
                    <path d="M18 9a6 6 0 1 0-12 0c0 6-2 7-2 7h16s-2-1-2-7" />
                    <path d="M13.7 20a2 2 0 0 1-3.4 0" />
                  </svg>
                  <span>발송된 알림이 없습니다</span>
                </div>
              ) : (
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>알림 ID</th>
                      <th>이벤트 유형</th>
                      <th>발송 시각</th>
                      <th>상태</th>
                      <th className="r" />
                    </tr>
                  </thead>
                  <tbody>
                    {resident.recentNotifications.map((notification) => (
                      <tr key={notification.notificationId}>
                        <td className="id">{notification.notificationId}</td>
                        <td className="ty">{eventTypeLabel(notification.eventType)}</td>
                        <td className="tm">
                          {formatDateTimeLabel(notification.sentAt ?? notification.createdAt)}
                        </td>
                        <td><StatusChip status={notification.status} /></td>
                        <td className="r">
                          <Link
                            to={`/app/notifications/${notification.notificationId}`}
                            className="golink"
                          >
                            상세
                            <svg viewBox="0 0 24 24"><path d="M5 12h13M12 5l7 7-7 7" /></svg>
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* 기본 정보 + 알림 수신 설정 */}
            <div className="glass g2 dcol" style={{ padding: 'var(--s5)' }}>
              <div className="zh2">
                <span className="zn">기본 정보</span>
                {!editing && (
                  <button type="button" className="btn btn-s" onClick={startEditing}>
                    수정
                  </button>
                )}
              </div>

              {editing ? (
                <div className="rnform">
                  <div className="au-row">
                    <label className="au-lab" htmlFor="rd-name">이름</label>
                    <input
                      className="au-in"
                      id="rd-name"
                      value={form.name}
                      onChange={(event) => setForm({ ...form, name: event.target.value })}
                    />
                  </div>
                  <div className="au-row">
                    <label className="au-lab" htmlFor="rd-phone">연락처</label>
                    <input
                      className="au-in num"
                      id="rd-phone"
                      value={form.phoneNumber}
                      onChange={(event) => setForm({ ...form, phoneNumber: event.target.value })}
                      autoComplete="off"
                    />
                  </div>
                  <div className="au-row">
                    <label className="au-lab" htmlFor="rd-building">동</label>
                    <input
                      className="au-in num"
                      id="rd-building"
                      value={form.buildingNumber}
                      onChange={(event) =>
                        setForm({ ...form, buildingNumber: event.target.value })
                      }
                      autoComplete="off"
                    />
                  </div>
                  <div className="au-row">
                    <label className="au-lab" htmlFor="rd-unit">호수</label>
                    <input
                      className="au-in num"
                      id="rd-unit"
                      value={form.unitNumber}
                      onChange={(event) => setForm({ ...form, unitNumber: event.target.value })}
                      autoComplete="off"
                    />
                  </div>
                  <div className="au-act">
                    <button
                      type="button"
                      className="btn btn-s"
                      onClick={() => {
                        setEditing(false)
                        setActionError(undefined)
                      }}
                      disabled={busy}
                    >
                      취소
                    </button>
                    <span className="grow" />
                    <button
                      type="button"
                      className="btn btn-p"
                      onClick={onSave}
                      disabled={busy}
                    >
                      {updateResident.isPending ? '저장 중…' : '저장'}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="info">
                  <div className="ir">
                    <span className="k">이름</span>
                    <span className="v">{resident.name}</span>
                  </div>
                  <div className="ir">
                    <span className="k">연락처</span>
                    <span className="v num">{resident.phoneNumber}</span>
                  </div>
                  <div className="ir">
                    <span className="k">동/호수</span>
                    <span className="v">
                      {resident.buildingNumber}동 {resident.unitNumber}호
                    </span>
                  </div>
                  <div className="ir">
                    <span className="k">등록 차량</span>
                    <span className="v num">{resident.vehicles.length}대</span>
                  </div>
                  <div className="ir">
                    <span className="k">위반 이력</span>
                    <span className="v num">{resident.violationCount}건</span>
                  </div>
                  <div className="ir">
                    <span className="k">알림 발송</span>
                    <span className="v num">{resident.notificationCount}건</span>
                  </div>
                  <div className="ir">
                    <span className="k">등록일</span>
                    <span className="v num">{formatDateTimeLabel(resident.createdAt)}</span>
                  </div>
                  <div className="ir">
                    <span className="k">최종 수정</span>
                    <span className="v num">{formatDateTimeLabel(resident.updatedAt)}</span>
                  </div>
                </div>
              )}

              {actionError && <p className="au-err" role="alert">{actionError}</p>}

              <div className="actwrap">
                <div className="actk">
                  {resident.notificationEnabled
                    ? '불법주차가 감지되면 이 세대에 안내 문자가 발송됩니다'
                    : '알림이 꺼져 있어 불법주차가 감지돼도 문자가 발송되지 않습니다'}
                </div>
                <div className="ntact">
                  <Link to="/app/residents" className="btn btn-s">목록으로</Link>
                  <button
                    type="button"
                    className={resident.notificationEnabled ? 'btn btn-s' : 'btn btn-p'}
                    onClick={onToggleNotification}
                    disabled={busy}
                  >
                    {changeNotification.isPending
                      ? '변경 중…'
                      : resident.notificationEnabled
                        ? '알림 수신 끄기'
                        : '알림 수신 켜기'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className={`toast${toast ? ' on' : ''}`} role="status" aria-live="polite">
        <svg viewBox="0 0 24 24"><path d="M4 12.5 9.5 18 20 6.5" /></svg>
        <span>{toast}</span>
      </div>
    </R0KiShell>
  )
}
