import { Suspense, lazy } from 'react'
import { createBrowserRouter } from 'react-router-dom'
import { HomeRoute } from './features/auth/HomeRoute'
import { RequireAuth } from './features/auth/RequireAuth'
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'
import SignupOnboarding from './pages/SignupOnboarding'
import PatrolList from './pages/PatrolList'
import PatrolDetail from './pages/PatrolDetail'
import EventList from './pages/EventList'
import EventDetail from './pages/EventDetail'
import RobotDetail from './pages/RobotDetail'
import RobotList from './pages/RobotList'
import RobotNew from './pages/RobotNew'
import NotificationList from './pages/NotificationList'
import NotificationDetail from './pages/NotificationDetail'
import MapFull from './pages/MapFull'
import NotFound from './pages/NotFound'
import RouteError from './pages/RouteError'

// 통계는 차트 라이브러리(recharts)를 쓰므로 청크 분리
const Stats = lazy(() => import('./pages/Stats'))
// 개발용 컴포넌트 갤러리 — 화면 어디서도 링크하지 않으므로 메인 번들에서 떼어낸다
// (여기서만 쓰는 UI 컴포넌트들이 함께 딸려 나간다)
const DevPreview = lazy(() => import('./pages/DevPreview'))
const TestMapSetup = lazy(() => import('./pages/TestMapSetup'))

// CLAUDE.md §6 라우트 매핑
export const router = createBrowserRouter([
  { path: '/', element: <HomeRoute />, errorElement: <RouteError /> },
  { path: '/login', element: <Login />, errorElement: <RouteError /> },
  { path: '/signup/onboarding', element: <SignupOnboarding />, errorElement: <RouteError /> },
  // 지도 확대 보기 (1h) — 지도 전용 풀스크린이라 /app 하위에 두지 않는다
  {
    path: '/app/test/map-setup',
    element: (
      <RequireAuth>
        <Suspense fallback={null}>
          <TestMapSetup />
        </Suspense>
      </RequireAuth>
    ),
    errorElement: <RouteError />,
  },
  {
    path: '/app/map',
    element: (
      <RequireAuth>
        <MapFull />
      </RequireAuth>
    ),
    errorElement: <RouteError />,
  },
  {
    path: '/app',
    errorElement: <RouteError />,
    children: [
      // R0-Ki 화면은 각자 자체 상단바 레이아웃(R0KiShell)을 쓴다 — 공통 래퍼 없이 독립 렌더
      {
        index: true,
        element: (
          <RequireAuth>
            <Dashboard />
          </RequireAuth>
        ),
      },
      {
        path: 'patrol',
        element: (
          <RequireAuth>
            <PatrolList />
          </RequireAuth>
        ),
      },
      {
        path: 'patrol/:id',
        element: (
          <RequireAuth>
            <PatrolDetail />
          </RequireAuth>
        ),
      },
      {
        path: 'events',
        element: (
          <RequireAuth>
            <EventList />
          </RequireAuth>
        ),
      },
      {
        path: 'events/:id',
        element: (
          <RequireAuth>
            <EventDetail />
          </RequireAuth>
        ),
      },
      // 알림 기록 (목록 → 상세) — 상단바 알림 버튼 목적지
      {
        path: 'notifications',
        element: (
          <RequireAuth>
            <NotificationList />
          </RequireAuth>
        ),
      },
      {
        path: 'notifications/:id',
        element: (
          <RequireAuth>
            <NotificationDetail />
          </RequireAuth>
        ),
      },
      // 로봇관리 (1i 목록 → 1j 등록 → 1i-r01 상세) — 모두 R0KiShell 자체 상단바
      {
        path: 'robots',
        element: (
          <RequireAuth>
            <RobotList />
          </RequireAuth>
        ),
      },
      {
        path: 'robots/new',
        element: (
          <RequireAuth>
            <RobotNew />
          </RequireAuth>
        ),
      },
      {
        path: 'robots/:id',
        element: (
          <RequireAuth>
            <RobotDetail />
          </RequireAuth>
        ),
      },
      // 통계 — recharts 청크 지연 로드
      {
        path: 'stats',
        element: (
          <RequireAuth>
            <Suspense fallback={null}>
              <Stats />
            </Suspense>
          </RequireAuth>
        ),
      },
    ],
  },
  {
    path: '/dev',
    element: (
      <Suspense fallback={null}>
        <DevPreview />
      </Suspense>
    ),
    errorElement: <RouteError />,
  },
  { path: '*', element: <NotFound /> },
])
