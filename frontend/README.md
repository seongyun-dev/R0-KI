# AI 순찰 로봇 프론트엔드

기존 디자인과 화면 구조를 유지하면서 백엔드 API 초안에 맞춘 통신 계층을 추가한 버전입니다.

## 실행

```bash
npm install
npm run dev
```

## 목업 / 실제 API 전환

`.env.example`을 `.env`로 복사한 뒤 값을 설정합니다.

```env
VITE_API_BASE_URL=http://localhost:8080
VITE_USE_MOCKS=true
VITE_DEFAULT_MAP_ID=1
VITE_DEFAULT_ROBOT_ID=1
VITE_STATS_ENDPOINT=/api/statistics
```

- `VITE_USE_MOCKS=true`: 기존 `src/mocks` 데이터를 사용합니다.
- `VITE_USE_MOCKS=false`: 실제 백엔드 API를 호출합니다.
- 로그인 응답에 `mapId`, `robotId`가 포함되면 환경변수보다 로그인 응답이 우선합니다.

## 적용된 API

| 기능 | API |
|---|---|
| 로그인 | `POST /api/auth/signin` |
| 일반 회원가입 | `POST /api/auth/signup` |
| 아파트 단지 검색 | `GET /api/auth/apartment-complexes?keyword=` |
| 이벤트 목록/상세 | `GET /api/events`, `GET /api/events/{eventId}` |
| 이벤트 처리 상태 | `PATCH /api/events/{eventId}/status` |
| 순찰 목록/상세 | `GET /api/patrols`, `GET /api/patrols/{patrolId}` |
| 순찰 이동 경로 | `GET /api/patrols/{patrolId}/path` |
| 로봇 목록/상세 | `GET /api/robots`, `GET /api/robots/{robotId}` |
| 로봇 등록/수정 | `POST /api/robots`, `PATCH /api/robots/{robotId}` |
| 지도 모니터링 | `GET /api/map/{mapId}/monitoring?robotId={robotId}` |
| 로봇 위치 SSE | `GET /api/robots/{robotId}/location/events` |
| 통계 | `VITE_STATS_ENDPOINT`에 설정된 경로 |

## 코드 구조

```text
src/api/contracts.ts   백엔드 요청/응답 DTO
src/api/client.ts      URL, Bearer 토큰, 공통 에러, SSE 처리
src/api/services.ts    기능별 API 함수
src/api/mappers.ts     백엔드 DTO → 기존 화면 모델 변환
src/features/**        페이지가 사용하는 조회/변경 훅
src/config/env.ts      환경 설정
```

페이지와 CSS는 기존 디자인을 유지하고, 기능 훅 아래의 데이터 공급 계층만 교체했습니다.

## 백엔드와 확정해야 하는 계약

1. 로그인 응답의 사용자, `mapId`, `robotId` 제공 방식
2. `resolution`, `originX`, `originY`, `width`, `height`를 포함한 SLAM 좌표 메타데이터
3. 신규 긴급 이벤트 SSE 또는 WebSocket
4. 통계 API 응답
5. 이벤트 `detectionConfidence`, `locationLabel`, 처리 메모
6. 로봇 모델, 담당 구역, 진단 부품, 누적 주행, 주간 가동률
7. 목록 API의 페이지네이션 형식
8. 날짜 ISO 8601 형식과 nullable 필드

지도 메타데이터가 없을 때는 체크포인트 좌표 범위를 기준으로 임시 정규화합니다. 실제 운영에서는 정확한 SLAM 메타데이터를 내려주는 것이 필수입니다.

## 검증

```bash
npm run lint
npm run build
```
