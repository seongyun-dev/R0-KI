import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { mapApi } from '../api/services'
import { R0KiAuthShell } from '../components/layout/R0KiAuthShell'
import { useAuthStore } from '../features/auth/useAuthStore'
import { StepMapScan } from '../features/onboarding/StepMapScan'
import { StepZones } from '../features/onboarding/StepZones'

type Mode = 'select' | 'scan' | 'zones'

export default function TestMapSetup() {
  const navigate = useNavigate()
  const robotId = useAuthStore((state) => state.robotId)
  const storedMapId = useAuthStore((state) => state.mapId)
  const setMapContext = useAuthStore((state) => state.setMapContext)
  const [mode, setMode] = useState<Mode>('select')
  const [mapId, setMapId] = useState<string | null>(storedMapId)
  const [isLoadingMap, setIsLoadingMap] = useState(storedMapId == null)
  const [mapLoadError, setMapLoadError] = useState<string>()

  useEffect(() => {
    if (storedMapId != null) return
    let active = true

    mapApi.current()
      .then((currentMap) => {
        if (!active) return
        const currentMapId = String(currentMap.mapId)
        setMapId(currentMapId)
        setMapContext({ mapId: currentMapId })
      })
      .catch((reason) => {
        if (active) {
          setMapLoadError(
            reason instanceof Error ? reason.message : '등록된 지도 정보를 확인하지 못했습니다.',
          )
        }
      })
      .finally(() => {
        if (active) setIsLoadingMap(false)
      })

    return () => {
      active = false
    }
  }, [setMapContext, storedMapId])

  const finish = () => navigate('/app', { replace: true })

  return (
    <R0KiAuthShell bootTagline="지도 재등록 테스트">
      <div className="au-wrap">
        <div className="glass g2 au-card w-map">
          <div className="au-brand"><span className="core" /><span>R0-Ki MAP TEST</span></div>
          <h1 className="au-h">지도·체크포인트 재등록</h1>
          <p className="au-sub">
            테스트 전용 화면입니다. 기존 서비스 화면에는 노출되지 않으며 저장하면 현재 단지의 데이터를 덮어씁니다.
          </p>

          {mode === 'select' && (
            <div className="au-panel">
              <p className="t">테스트할 작업을 선택하세요.</p>
              <p className="s">새 지도를 등록하면 단지의 기존 지도 파일과 지도 정보가 교체됩니다.</p>
              <div className="au-act">
                <button type="button" className="btn btn-s" onClick={finish}>대시보드로</button>
                <span className="grow" />
                <button
                  type="button"
                  className="btn btn-s"
                  disabled={mapId == null || isLoadingMap}
                  onClick={() => setMode('zones')}
                >
                  현재 지도 체크포인트 재설정
                </button>
                <button
                  type="button"
                  className="btn btn-p"
                  disabled={robotId == null}
                  onClick={() => setMode('scan')}
                >
                  새 지도 등록
                </button>
              </div>
              {robotId == null && <p className="t bad">등록된 로봇이 없어 새 매핑을 시작할 수 없습니다.</p>}
              {isLoadingMap && <p className="s">현재 단지의 등록 지도를 확인하고 있습니다.</p>}
              {!isLoadingMap && mapId == null && (
                <p className="t bad">
                  {mapLoadError ?? '등록된 지도가 없어 체크포인트만 재설정할 수 없습니다.'}
                </p>
              )}
            </div>
          )}

          {mode === 'scan' && robotId != null && (
            <StepMapScan
              robotId={robotId}
              onPrev={() => setMode('select')}
              onNext={(completedMapId) => {
                const nextMapId = String(completedMapId)
                setMapId(nextMapId)
                setMapContext({ mapId: nextMapId, robotId })
                setMode('zones')
              }}
            />
          )}

          {mode === 'zones' && mapId != null && (
            <>
              <div className="au-note">
                <span><b>주의:</b> 저장하면 기존 체크포인트 전체가 현재 작성 내용으로 교체됩니다.</span>
              </div>
              <StepZones
                mapId={mapId}
                replaceExisting
                onPrev={() => setMode('select')}
                onComplete={finish}
              />
            </>
          )}
        </div>
      </div>
    </R0KiAuthShell>
  )
}
