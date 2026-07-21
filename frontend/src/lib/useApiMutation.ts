import { useCallback, useState } from 'react'

export function useApiMutation<TVariables, TResult>(
  mutate: (variables: TVariables) => Promise<TResult>,
) {
  const [isPending, setPending] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const mutateAsync = useCallback(
    async (variables: TVariables) => {
      setPending(true)
      setError(null)
      try {
        return await mutate(variables)
      } catch (reason) {
        const next = reason instanceof Error ? reason : new Error('요청을 처리하지 못했습니다')
        setError(next)
        throw next
      } finally {
        setPending(false)
      }
    },
    [mutate],
  )

  return {
    mutateAsync,
    isPending,
    isError: Boolean(error),
    error,
    reset: () => setError(null),
  }
}
