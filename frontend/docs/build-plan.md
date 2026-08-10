# 빌드 플랜 (Claude Code 세션 순서)

한 번에 다 하지 말고 아래 마일스톤을 **순서대로**, 각 단계마다 확인 후 다음으로.
각 화면은 **와이어프레임 그대로**(docs/screens.md) + 토큰 적용. 완료 기준: 반응형 + 접근성 + 빈/로딩/에러 상태.

## M0 — 프로젝트 셋업
- [ ] `npm create vite@latest . -- --template react-ts`
- [ ] 의존성 설치(README 참고): tailwind/postcss/autoprefixer, react-router-dom, three @react-three/fiber @react-three/drei, lenis, clsx tailwind-merge, (선택) @tanstack/react-query zustand recharts
- [ ] `tailwind.config.js` · `postcss.config.js` · `src/styles/tokens.css` · `src/styles/global.css` 배치, `main.tsx`에서 global.css import
- [ ] `src/lib/cn.ts`(clsx+tailwind-merge), 기본 라우터 골격
- [ ] 확인: 토큰 색/폰트가 화면에 적용되는지 샘플로 검증

## M1 — 디자인 시스템(프리미티브)
- [ ] `ui/`: Button/Pill, Card, StatTile, StatusBadge, Tag, Field(Input/Textarea/Select/Checkbox), Modal, Drawer, Toast, Table, Stepper, ProgressBar, Breadcrumb, Tabs, EmptyState, Skeleton
- [ ] `icons/`: 필요한 인라인 SVG(스트로크 스타일 통일)
- [ ] 간단한 미리보기 페이지(`/dev`)로 컴포넌트 눈으로 확인(선택)

## M2 — 도메인 타입 & 목업
- [ ] `types/domain.ts` (Robot, Patrol, PatrolPoint, Event, Zone, Stat 등 — 파일 참고)
- [ ] `mocks/`: 와이어프레임 예시값으로 목업 데이터(P-1042, E-3312, R-01, 통계 수치 등)
- [ ] 데이터 훅: `usePatrols/usePatrol`, `useEvents/useEvent`, `useRobot`, `useStats` (지금은 목업 반환, 나중에 API 교체)

## M3 — 레이아웃 & 랜딩
- [ ] `layout/`: SiteHeader/Footer, AppShell(Header+Sidebar+PageHeader)
- [ ] 라우터 완성(docs/screens.md 라우트 표대로)
- [ ] **랜딩 `/`** 이식: landing.html → React 컴포넌트로. 3D `PatrolRobot`(R3F) 포함. 섹션/모달/스무스스크롤/리빌.

## M4 — 인증 & 회원가입
- [ ] `/login` (1a)
- [ ] `/signup` 일반 (1t) + 아파트단지 검색 모달 (유효성/강도/중복확인/자동하이픈)
- [ ] `/signup/onboarding` 5스텝 (1u→1v→1w→1x). Stepper 공통. 맵 스캔 진행률/구역 드래그(1y)는 인터랙티브

## M5 — 순찰 관리
- [ ] 목록 `/app/patrol` (1d): 필터바 + DataTable(컬럼 그대로)
- [ ] 상세 `/app/patrol/:id` (1e): 요약 + 경로지도 + 타임라인 + **PATROL REPORT**(AI요약/탐지이벤트/이상징후/지점기록 테이블) + PDF 다운로드 버튼

## M6 — 이벤트 관리
- [ ] 목록 `/app/events` (1f): 필터 + 테이블
- [ ] 상세 `/app/events/:id` (1g): 증거 이미지 + 메타 + **상태변경 모달**

## M7 — 로봇 관리
- [ ] 상세 `/app/robots/:id` (1i): 프로필/지표/부품상태/LIVE DIAGNOSTICS/상태리포트/최근순찰/AI진단
- [ ] 등록 `/app/robots/new` (1j): QR/직접입력
- [ ] 수정 Drawer + Toast (1k)

## M8 — 대시보드 & 통계
- [ ] 대시보드 `/app` (1c): 지도 + 최근 이벤트 + 로봇 상태 요약
- [ ] 통계 `/app/stats` (1m): KPI 4 + 일자별 추이(라인) + 시간대별(누적 막대) + CSV

## M9 — 마감
- [ ] 반응형 전수 점검, 접근성(키보드/포커스/aria), 빈/로딩/에러 상태
- [ ] 라우트 가드(비로그인 → /login), 404
- [ ] 성능(3D 지연 로드/리듀스드모션), lint/타입 클린

> 팁: 각 마일스톤 시작 시 Claude Code에게 "docs/screens.md의 해당 화면을 와이어프레임 그대로, 토큰만 적용해서 만들어줘. 목업은 mocks/ 사용" 식으로 지시.
