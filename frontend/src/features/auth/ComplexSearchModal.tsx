import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { SearchIcon } from '../../components/icons'
import { Button, EmptyState, Input, Modal, Skeleton } from '../../components/ui'
import type { Complex } from '../../types/domain'
import { useComplexSearch } from './useComplexSearch'

export type ComplexSearchModalProps = {
  open: boolean
  onClose: () => void
  onSelect: (complex: Complex) => void
}

/** 아파트단지 검색 모달 (1t) — 결과 없으면 최초 가입자 온보딩 유도 */
export function ComplexSearchModal({ open, onClose, onSelect }: ComplexSearchModalProps) {
  const navigate = useNavigate()
  const [input, setInput] = useState('')
  const [keyword, setKeyword] = useState('')
  const { data: results, isLoading } = useComplexSearch(keyword)

  return (
    <Modal open={open} onClose={onClose} title="아파트단지 검색" className="max-w-lg">
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          setKeyword(input)
        }}
      >
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="아파트 이름/주소"
          aria-label="아파트 이름/주소"
        />
        <Button type="submit" variant="dark" className="flex-none">
          <SearchIcon />
          검색
        </Button>
      </form>

      <div className="mt-5 max-h-72 overflow-y-auto">
        {isLoading ? (
          <div className="flex flex-col gap-3 py-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-2/3" />
          </div>
        ) : results && results.length > 0 ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-xs font-semibold text-muted">
                <th scope="col" className="px-2 py-2 text-left">아파트 이름</th>
                <th scope="col" className="px-2 py-2 text-left">도로명주소</th>
                <th scope="col" className="px-2 py-2" aria-label="선택" />
              </tr>
            </thead>
            <tbody>
              {results.map((c) => (
                <tr key={c.id} className="border-b border-line">
                  <td className="px-2 py-3 font-semibold">{c.name}</td>
                  <td className="px-2 py-3 text-muted">{c.roadAddress}</td>
                  <td className="px-2 py-3 text-right">
                    <Button size="sm" variant="outline" onClick={() => onSelect(c)}>
                      선택
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState
            title="검색 결과가 없습니다"
            description="찾으시는 단지가 없다면 신규 아파트단지로 등록해주세요"
            action={
              <Button size="sm" variant="dark" onClick={() => navigate('/signup/onboarding')}>
                신규 아파트단지 등록 →
              </Button>
            }
          />
        )}
      </div>

      <p className="mt-5 border-t border-line pt-4 text-center text-sm text-muted">
        찾으시는 단지가 없으신가요?{' '}
        <button
          type="button"
          onClick={() => navigate('/signup/onboarding')}
          className="font-semibold text-fg underline-offset-4 hover:underline"
        >
          신규 아파트단지 등록(최초 가입자) →
        </button>
      </p>
    </Modal>
  )
}
