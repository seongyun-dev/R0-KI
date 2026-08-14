# Frontend — R0-Ki 관제 웹

아파트 AI 순찰 로봇 **R0-Ki** 관리자용 웹앱입니다. React로 관제 대시보드·온보딩·통계를 제공하고, Backend REST/SSE와 연동합니다.

루트 프로젝트 설명: [../README.md](../README.md)

---

## 기술 스택

| 영역 | 선택 |
| --- | --- |
| UI | React 18, TypeScript |
| 빌드 | Vite 8 |
| 라우팅 | react-router-dom v6 |
| 상태 | Zustand (`persist`) |
| 스타일 | Tailwind CSS 3 + 커스텀 CSS |
| 3D | Three.js, `@react-three/fiber`, `@react-three/drei` |
| 차트 | Recharts |
| PDF | jspdf + html2canvas |
| 배포 | Dockerfile, nginx |

---

## 실행

```bash
cd frontend
npm install
cp .env.example .env   # 필요 시 수정
npm run dev
```

### 환경 변수 (이름만)

| 키 | 용도 |
| --- | --- |
| `VITE_API_BASE_URL` | Backend origin (예: `http://localhost:8080`) |
| `VITE_DEFAULT_MAP_ID` | 로그인 응답에 mapId가 없을 때 개발용 기본값 |
| `VITE_DEFAULT_ROBOT_ID` | 로그인 응답에 robotId가 없을 때 개발용 기본값 |

실제 토큰·운영 URL은 `.env`에만 두고 Git에 커밋하지 않습니다.

### 검증

```bash
npm run lint
npm run build
npm run test:map-coordinates
npm run test:dashboard-25d
npm run test:display-geometry-25d
```

---

## 코드 구조

```text
frontend/src/
├── api/
│   ├── client.ts          # fetch, envelope unwrap, SSE, blob
│   ├── contracts.ts       # Backend DTO
│   ├── services.ts        # auth / events / patrols / robots / map …
│   └── mappers.ts         # DTO → 화면 domain
├── config/env.ts
├── features/              # 도메인 훅·UI
│   ├── auth/
│   ├── dashboard/         # 지도, SSE, MJPEG, 좌표
│   ├── onboarding/
│   └── stats/
├── pages/                 # 라우트 페이지
├── components/            # ui, layout(R0KiShell), robot(3D)
├── types/domain.ts
└── styles/
```

데이터 흐름: **페이지 → features 훅 → api/services → client → mappers → domain**.

---

## 주요 화면

| 경로 | 역할 |
| --- | --- |
| `/` | 랜딩 또는 로그인 분기 |
| `/login` | 로그인 |
| `/signup/onboarding` | 계정·단지·로봇·맵핑·구역/웨이포인트 |
| `/app` | 관제 대시보드 (지도 + 라이브캠 + 이벤트) |
| `/app/map` | 지도 풀스크린 |
| `/app/patrol`, `/app/patrol/:id` | 순찰 이력·상세 |
| `/app/events`, `/app/events/:id` | 탐지 이벤트 |
| `/app/robots` … | 로봇 CRUD·진단 |
| `/app/residents` … | 입주민·차량 |
| `/app/notifications` … | 알림 이력 |
| `/app/stats` | 통계 차트 + AI 인사이트 (lazy) |

라우트 정의: `src/router.tsx` (`RequireAuth` 가드).

---

## 핵심 로직

### 1. 인증 SSE 클라이언트

`src/api/client.ts`에서 `EventSource` 대신 `fetch` + `ReadableStream`으로 SSE를 파싱합니다. Bearer 토큰, `event:`/`data:` 라인, heartbeat 무시, `AbortController` 재연결을 처리합니다.

구독 예:

- 로봇 위치·상태: `useRobotLocations` → `/api/robots/.../location/events` 등
- 긴급 이벤트: `useEmergencyAlert` → `/api/events/subscribe/emergency`
- 일반(순찰 완료 등): `/api/events/subscribe/general`
- 장애물: `/api/robots/obstacle-events`
- 맵핑 세션: mapping session SSE

### 2. SLAM 좌표 → 2.5D 지도

Backend가 주는 `resolution`, `origin`, `width`, `height`로 월드 좌표를 그리드에 투영합니다.

- `features/dashboard/mapCoordinates.ts`, `mapCoordinateMetadata.ts`
- `ComplexMap25D.tsx`, `mapProjection25d.ts` — 아이소메트릭 벽·구역·경로
- `displayGeometry25d.ts` — 점유 마스크 표시용 노이즈 정리

관련 단위 테스트: `tests/mapCoordinates25d.test.ts` 등.

### 3. MJPEG 라이브캠

`useMjpegStream.ts`: 스트림 세션 토큰 → 바이너리에서 JPEG 마커 분리 → blob URL. 상태 `idle | connecting | live | failed` 및 재시도.

### 4. AI 인사이트·통계

- `useAnalyticsInsight.ts`: 주/월 인사이트 상태가 `PENDING`/`PROCESSING`이면 약 3초 폴링
- Recharts: 추이·구역·처리·시간대 차트
- `exportStatsPdf.ts`: 화면 캡처 후 PDF

### 5. 온보딩·Nav2 계약

맵핑 SSE 진행 → 구역/웨이포인트 드래그 편집. `navigationEditor.ts`에서 acceptance radius 등 Nav2 계약 범위를 검증합니다.

### 6. 3D 로봇 UI

- 랜딩·맵: `PatrolRobot`, `MapLiveScene`
- 상세 진단: `RobotDiagnosticView` — 부위 앵커 투영 + CSS 지시선

### 7. 인증 스토어

`useAuthStore`: JWT `exp` 파싱, remember me(local/session), 계정별 `mapId`/`robotId` 컨텍스트.

---

## 주요 API 연동

| 기능 | API |
| --- | --- |
| 로그인 / 나 | `POST /api/auth/signin`, `GET /api/auth/me` |
| 회원가입·이메일 | `POST /api/auth/signup`, email send/verify |
| 이벤트 | `GET /api/events`, `PATCH .../status`, SSE subscribe |
| 순찰 | `POST /api/patrols`, stop, list, detail, PDF |
| 로봇 | CRUD, location/obstacle SSE, stream session |
| 지도·존·웨이포인트 | `/api/map/**` |
| 맵핑 세션 | `/api/map/mapping-sessions` + SSE |
| 통계 | `/api/analytics/events/*` |
| 인사이트 | `/api/analytics/insights` |
| 입주민 | `/api/residents` |

공통: 응답 envelope `{ success, data }` unwrap, 목록의 `content|items|data` 흡수는 `client.ts` / `services.ts`에 있습니다.

---

## 추가 문서

- [docs/screens.md](docs/screens.md) — 화면 목록
- [docs/components.md](docs/components.md) — 컴포넌트
- [docs/design-tokens.md](docs/design-tokens.md) — 디자인 토큰
