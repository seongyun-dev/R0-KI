# Front 순찰 경로 설정 인수인계

## 작업 기준

- 작업 브랜치: `front/feat/ordered-waypoint-config`
- 기준 브랜치/커밋: `origin/front/dev` / `52cce95`
- 병합 대상: `front/dev` 검증 후 `front/master`
- 이 문서와 변경에는 운영 배포나 비밀정보가 포함되지 않는다.

## 변경 내용

1. 지도 생성 안내를 실제 시연 절차인 `프론트에서 시작 → 게임패드 수동 주행 → 종료 및 저장` 흐름으로 수정했다.
2. 구역 편집 뒤 별도의 순찰 경로 편집 단계를 추가했다.
3. 지도 클릭으로 순서가 있는 경유 지점을 추가하고, 순서 변경·삭제 및 동작 선택을 할 수 있다.
4. 경유 지점 동작은 다음 세 종류다.
   - `PASS`: 그대로 통과
   - `SCAN`: 촬영·탐지
   - `DESTINATION`: 순찰 종료
5. 하나의 주차 구역에 여러 `SCAN` 지점을 배치할 수 있으며, 구역 중심점 하나를 경로로 자동 변환하지 않는다.
6. 구역 저장은 append API가 아니라 지도 버전을 포함한 atomic replace API를 사용한다.
7. 사용자가 요청한 단순화 사항을 반영했다.
   - 벽·미확인 셀 경고와 키보드 안내 제거
   - 안내 문구를 `지도 위를 눌러 실제 경유 지점을 추가하세요.`로 단순화
   - `DESTINATION` 영문 병기 제거
   - 연결 구역 선택과 고급 설정 UI 제거
   - 원시 좌표 대신 `지도 위치 B4` 형태의 대략적 위치 표시

## 주요 파일

- `frontend/src/features/onboarding/StepMapScan.tsx`: 수동 mapping 안내
- `frontend/src/features/onboarding/StepZones.tsx`: 구역/경로 단계 연결, 구역 replace 저장
- `frontend/src/features/onboarding/StepWaypoints.tsx`: ordered waypoint 편집 화면
- `frontend/src/features/onboarding/mapCoordinates.ts`: 화면 좌표와 map 좌표 변환
- `frontend/src/features/onboarding/navigationEditor.ts`: 경로 편집과 유효성 검사
- `frontend/src/pages/SignupOnboarding.tsx`: onboarding 단계 연결
- `frontend/src/api/contracts.ts`, `frontend/src/api/services.ts`: waypoint/zone 계약과 API
- `frontend/src/styles/r0ki.css`: 기존 onboarding 스타일에 맞춘 반응형 배치
- `docs/verification/*.png`: 데스크톱·좁은 화면 검증 캡처

## API 계약

- 구역 교체: `PUT /api/map/{mapId}/zones`
- 경유 지점 조회: `GET /api/map/{mapId}/waypoints`
- 경유 지점 교체: `PUT /api/map/{mapId}/waypoints`
- 교체 요청은 현재 `mapVersion`을 포함한다.
- waypoint 최소 필드: `sequence`, `x`, `y`, `action`
- 선택 필드: `yaw`, `acceptanceRadius`, `zoneId`

## 저장 전 검증

- 순번이 1부터 끊기지 않아야 한다.
- 마지막 지점 하나만 `DESTINATION`이어야 한다.
- 모든 지점은 지도 범위 안에 있어야 한다.
- 도착 반경은 0.2~1.0m이며 UI 기본값은 0.3m다.
- 연속 지점 간 거리가 두 지점 도착 반경의 합보다 커야 한다.
- 연결된 zone이 있다면 현재 지도에 존재해야 한다.
- 현재 UI는 `originYaw=0`인 지도를 지원한다. 회전된 occupancy map은 저장하지 않고 오류를 표시한다.

## 검증 결과

- `npm run lint`: 성공. 기존 fast-refresh 경고 9개만 존재한다.
- `npm run build`: 성공.
- Node 20.17에서 실행했으며 Vite 권장 버전 경고와 기존 500kB 초과 chunk 경고가 있다.
- 브라우저 검증: 1440×900, 560×900에서 marker/번호/동작 변경/재정렬/삭제/저장 검증을 수행했다.
- 560px 화면에서 가로 overflow가 없고, 세로 스크롤과 경로 목록 내부 스크롤이 정상 동작한다.

## 캡처

- `docs/verification/zone-editor-desktop.png`
- `docs/verification/waypoint-editor-desktop.png`
- `docs/verification/waypoint-editor-narrow.png`
- `docs/verification/waypoint-editor-narrow-bottom.png`

## 다음 작업자 확인 사항

- Back의 V15 migration과 waypoint API가 먼저 반영된 환경에서 저장/재조회 E2E를 확인한다.
- 실제 저장 지도에서 map metadata의 `originYaw`가 0인지 확인한다.
- 지도 위 셀 표시는 운영자가 위치를 구분하기 위한 UI이며, 실제 주행에는 내부의 정확한 map 좌표가 사용된다.
- 현재 UI에서 숨긴 `yaw`, `acceptanceRadius`, `zoneId`는 기본값 또는 자동 계산값으로 계약에 유지된다.
