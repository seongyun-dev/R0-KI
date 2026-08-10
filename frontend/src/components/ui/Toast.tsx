import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from 'react'

type ToastItem = { id: number; message: string }

const ToastContext = createContext<(message: string) => void>(() => {})

/** 사용: const toast = useToast(); toast('✓ 저장되었습니다') */
export function useToast() {
  return useContext(ToastContext)
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const idRef = useRef(0)

  const toast = useCallback((message: string) => {
    const id = ++idRef.current
    setItems((s) => [...s, { id, message }])
    setTimeout(() => setItems((s) => s.filter((t) => t.id !== id)), 2600)
  }, [])

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed inset-0 z-[60] flex flex-col items-center justify-center gap-3 px-4"
      >
        {items.map((t) => (
          <div
            key={t.id}
            className="rounded-card bg-success px-10 py-6 text-lg font-bold text-white shadow-pop"
          >
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
