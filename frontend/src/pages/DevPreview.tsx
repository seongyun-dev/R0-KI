import { useState } from 'react'
import {
  Breadcrumb,
  Button,
  Card,
  Checkbox,
  DataTable,
  Drawer,
  EmptyState,
  Eyebrow,
  Field,
  IconButton,
  Input,
  Modal,
  ProgressBar,
  Select,
  Skeleton,
  StatTile,
  StatusBadge,
  Stepper,
  Tabs,
  Tag,
  Textarea,
  useToast,
  type Column,
} from '../components/ui'
import { CloseIcon, DownloadIcon, SearchIcon } from '../components/icons'
import { usePatrols } from '../features/patrol/usePatrols'
import type { Patrol } from '../types/domain'

const swatches = [
  { cls: 'bg-accent', name: 'accent' },
  { cls: 'bg-accent-light', name: 'accent-light' },
  { cls: 'bg-accent-deep', name: 'accent-deep' },
  { cls: 'bg-accent-soft', name: 'accent-soft' },
  { cls: 'bg-surface', name: 'surface' },
  { cls: 'bg-surface-2', name: 'surface-2' },
  { cls: 'bg-card', name: 'card' },
  { cls: 'bg-ink', name: 'ink' },
  { cls: 'bg-success', name: 'success' },
  { cls: 'bg-info', name: 'info' },
  { cls: 'bg-warning', name: 'warning' },
  { cls: 'bg-danger', name: 'danger' },
]

// M2 스모크 테스트 — mocks/patrols + usePatrols() 훅 배선
const demoColumns: Column<Patrol>[] = [
  { key: 'id', header: '순찰ID', render: (r) => <span className="font-mono font-semibold tabular">{r.id}</span> },
  { key: 'start', header: '시작', render: (r) => <span className="font-mono tabular">{r.date} {r.start}</span> },
  { key: 'end', header: '종료', render: (r) => <span className="font-mono tabular">{r.end ?? '-'}</span> },
  { key: 'route', header: '순찰 경로', render: (r) => r.routeZones.join(' → ') },
  { key: 'events', header: '이벤트', render: (r) => <span className="font-mono tabular">{r.eventCount}</span>, align: 'right' },
  { key: 'status', header: '상태', render: (r) => <StatusBadge label={r.status} bracket /> },
]

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-12">
      <h2 className="mb-4 text-sm font-bold text-muted">{title}</h2>
      {children}
    </section>
  )
}

// /dev — M0 토큰 검증 + M1 프리미티브 미리보기
export default function DevPreview() {
  const toast = useToast()
  const [modalOpen, setModalOpen] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [tab, setTab] = useState('all')
  const { data: patrolRows, isLoading: patrolsLoading } = usePatrols()

  return (
    <main className="mx-auto max-w-shell px-6 py-12">
      <Eyebrow>DEV · 디자인 시스템 미리보기</Eyebrow>
      <h1 className="mt-3 text-4xl font-bold tracking-tight">AI 순찰 로봇 관리 시스템</h1>
      <p className="mt-2 text-muted">
        Pretendard sans · <span className="font-mono tabular">0123456789 07/15 09:00</span> mono
      </p>

      <Section title="TOKENS">
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
          {swatches.map((s) => (
            <div key={s.cls} className="overflow-hidden rounded-card-sm ring-1 ring-line">
              <div className={`h-12 ${s.cls}`} />
              <div className="px-2.5 py-1.5 font-mono text-xs text-muted">{s.name}</div>
            </div>
          ))}
        </div>
      </Section>

      <Section title="BUTTON / PILL">
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="accent" withArrow="right">도입 문의</Button>
          <Button variant="dark" withArrow="up-right">대시보드 보기</Button>
          <Button variant="light">가입 완료</Button>
          <Button variant="outline">중복확인</Button>
          <Button variant="ghost">취소</Button>
          <Button variant="dark" loading>저장 중</Button>
          <Button variant="accent" size="sm">PDF 다운로드</Button>
          <Button variant="dark" size="lg" withArrow="right">다음: 로봇 등록</Button>
          <IconButton label="닫기" variant="light"><CloseIcon /></IconButton>
          <IconButton label="검색" variant="dark"><SearchIcon /></IconButton>
        </div>
      </Section>

      <Section title="STATUS BADGE / TAG / EYEBROW">
        <div className="flex flex-wrap items-center gap-3">
          {['완료', '순찰중', '진행중', '확인중', '미처리', '점검필요', '긴급', '침입', '대기'].map((l) => (
            <StatusBadge key={l} label={l} bracket />
          ))}
          <Tag>AI 이상탐지</Tag>
          <Eyebrow bordered>주요 기능</Eyebrow>
        </div>
      </Section>

      <Section title="STAT TILE">
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatTile value="142회" label="총 순찰 횟수" delta={{ text: '전주 +8%', direction: 'up' }} />
          <StatTile value="83건" label="총 이벤트" delta={{ text: '전주 +15%', direction: 'up' }} />
          <StatTile value="12분" label="평균 처리시간" delta={{ text: '-3분', direction: 'down' }} />
          <StatTile value="94%" label="가동률" delta={{ text: '목표 90% 초과', direction: 'neutral' }} tone="dark" />
        </div>
      </Section>

      <Section title="FIELD">
        <Card className="max-w-md p-7">
          <div className="flex flex-col gap-5">
            <Field label="아이디" htmlFor="dev-id" required hint="4~20자 영문/숫자">
              <div className="flex gap-2">
                <Input id="dev-id" placeholder="아이디 입력" />
                <Button variant="outline" className="flex-none">중복확인</Button>
              </div>
            </Field>
            <Field label="비밀번호" htmlFor="dev-pw" required error="비밀번호가 일치하지 않습니다">
              <Input id="dev-pw" type="password" placeholder="비밀번호 입력" invalid />
            </Field>
            <Field label="상태" htmlFor="dev-status">
              <Select id="dev-status" defaultValue="확인중">
                <option>확인중</option>
                <option>완료</option>
                <option>미처리</option>
              </Select>
            </Field>
            <Field label="메모" htmlFor="dev-memo">
              <Textarea id="dev-memo" placeholder="메모를 입력하세요" />
            </Field>
            <Checkbox label="이용약관 및 개인정보처리방침에 동의합니다" />
          </div>
        </Card>
      </Section>

      <Section title="DATA TABLE">
        <Card className="p-2">
          <DataTable
            columns={demoColumns}
            rows={patrolRows ?? []}
            rowKey={(r) => r.id}
            loading={patrolsLoading}
            onRowClick={(r) => toast(`${r.id} 클릭`)}
          />
        </Card>
      </Section>

      <Section title="STEPPER / PROGRESS">
        <div className="flex flex-col gap-6">
          <Stepper steps={['계정·단지', '로봇 등록', '맵 등록']} current={1} />
          <ProgressBar value={68} label="맵 스캔 진행률" className="max-w-sm" />
        </div>
      </Section>

      <Section title="BREADCRUMB / TABS">
        <div className="flex flex-col gap-4">
          <Breadcrumb items={[{ label: 'Dashboard', to: '/app' }, { label: '순찰관리', to: '/app/patrol' }, { label: 'P-1042' }]} />
          <Tabs
            items={[{ value: 'all', label: '전체' }, { value: 'open', label: '미처리' }, { value: 'done', label: '완료' }]}
            value={tab}
            onChange={setTab}
          />
        </div>
      </Section>

      <Section title="OVERLAY — Modal / Drawer / Toast">
        <div className="flex flex-wrap gap-3">
          <Button variant="dark" onClick={() => setModalOpen(true)}>상태 변경 모달</Button>
          <Button variant="outline" onClick={() => setDrawerOpen(true)}>수정 드로어</Button>
          <Button variant="light" onClick={() => toast('✓ 저장되었습니다')}>토스트</Button>
        </div>
      </Section>

      <Section title="EMPTY / SKELETON">
        <div className="grid gap-4 sm:grid-cols-2">
          <EmptyState
            title="표시할 이벤트가 없습니다"
            description="필터를 변경해 다시 검색해보세요"
            action={<Button variant="outline" size="sm">필터 초기화</Button>}
          />
          <Card className="flex flex-col gap-3 p-6">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-24 w-full" />
          </Card>
        </div>
      </Section>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="처리 상태 변경">
        <div className="flex flex-col gap-4">
          <Field label="상태" htmlFor="modal-status">
            <Select id="modal-status" defaultValue="확인중">
              <option>확인중</option>
              <option>완료</option>
              <option>미처리</option>
            </Select>
          </Field>
          <Field label="메모" htmlFor="modal-memo">
            <Textarea id="modal-memo" placeholder="처리 내용을 입력하세요" />
          </Field>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setModalOpen(false)}>취소</Button>
            <Button
              variant="dark"
              onClick={() => {
                setModalOpen(false)
                toast('✓ 저장되었습니다')
              }}
            >
              저장
            </Button>
          </div>
        </div>
      </Modal>

      <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)} title="로봇 수정">
        <div className="flex flex-col gap-5">
          <Field label="로봇명" htmlFor="drawer-name">
            <Input id="drawer-name" defaultValue="R-01" />
          </Field>
          <Field label="담당 구역" htmlFor="drawer-zone">
            <Select id="drawer-zone" defaultValue="101~103동">
              <option>101~103동</option>
              <option>전체</option>
            </Select>
          </Field>
          <Field label="상태" htmlFor="drawer-status">
            <Select id="drawer-status" defaultValue="순찰중">
              <option>순찰중</option>
              <option>대기</option>
              <option>충전중</option>
            </Select>
          </Field>
          <Button
            variant="dark"
            onClick={() => {
              setDrawerOpen(false)
              toast('✓ 저장되었습니다')
            }}
          >
            저장
          </Button>
        </div>
      </Drawer>

      <div className="mt-16 flex items-center gap-3 border-t border-line pt-6 text-sm text-muted">
        <DownloadIcon /> 아이콘 스트로크 스타일 확인용
      </div>
    </main>
  )
}
