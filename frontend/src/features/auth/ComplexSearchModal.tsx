import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { R0KiModal } from '../../components/layout/R0KiModal'
import type { Complex } from '../../types/domain'
import { useComplexSearch } from './useComplexSearch'

export type ComplexSearchModalProps = {
  open: boolean
  onClose: () => void
  onSelect: (complex: Complex) => void
}

/** 아파트단지 검색 모달 (1t) — 결과 없으면 최초 가입자 온보딩 유도. R0Ki 유리 모달 */
export function ComplexSearchModal({ open, onClose, onSelect }: ComplexSearchModalProps) {
  const navigate = useNavigate()
  const [input, setInput] = useState('')
  const [keyword, setKeyword] = useState('')
  const { data: results, isLoading } = useComplexSearch(keyword)

  return (
    <R0KiModal open={open} onClose={onClose} title="아파트단지 검색">
      <form
        className="au-pair"
        onSubmit={(e) => {
          e.preventDefault()
          setKeyword(input)
        }}
      >
        <span className="au-srch">
          <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.2-3.2" /></svg>
          <input
            className="au-in"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="아파트 이름/주소"
            aria-label="아파트 이름/주소"
          />
        </span>
        <button type="submit" className="btn btn-p">검색</button>
      </form>

      <div className="srchlist">
        {isLoading ? (
          <div className="srchbusy"><span className="au-spin" role="status" aria-label="검색 중" /></div>
        ) : results && results.length > 0 ? (
          results.map((c) => (
            <div className="srow" key={c.id}>
              <span className="nm">{c.name}</span>
              <span className="ad">{c.roadAddress}</span>
              <button type="button" className="btn btn-s" onClick={() => onSelect(c)}>
                선택
              </button>
            </div>
          ))
        ) : (
          <div className="empty">
            <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.2-3.2" /></svg>
            <span>검색 결과가 없습니다</span>
          </div>
        )}
      </div>

      <div className="au-foot">
        찾으시는 단지가 없으신가요?{' '}
        <button type="button" onClick={() => navigate('/signup/onboarding')}>
          신규 아파트단지 등록(최초 가입자) →
        </button>
      </div>
    </R0KiModal>
  )
}
