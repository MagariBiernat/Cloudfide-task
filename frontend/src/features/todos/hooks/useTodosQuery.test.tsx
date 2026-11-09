import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, expect, it, vi } from 'vitest'
import { todoKeys } from '../api/queryKeys'
import { todosApi } from '../api/todos'
import { todoFixture } from '../../../test/todoFixture'
import { useTodosQuery } from './useTodosQuery'

vi.mock('../api/todos', () => ({ todosApi: { list: vi.fn() } }))

let client: QueryClient
beforeEach(() => {
  vi.clearAllMocks()
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={client}>{children}</QueryClientProvider>
)

it('returns the list fetched from the API and caches it', async () => {
  vi.mocked(todosApi.list).mockResolvedValue([todoFixture])
  const { result } = renderHook(() => useTodosQuery(), { wrapper })
  await waitFor(() => expect(result.current.data).toEqual([todoFixture]))
  expect(client.getQueryData(todoKeys.list)).toEqual([todoFixture])
})

it('passes an AbortSignal to the API', async () => {
  vi.mocked(todosApi.list).mockResolvedValue([])
  const { result } = renderHook(() => useTodosQuery(), { wrapper })
  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  expect(todosApi.list).toHaveBeenCalledWith(expect.any(AbortSignal))
})

it('exposes the error when the request fails', async () => {
  vi.mocked(todosApi.list).mockRejectedValue(new Error('Network down'))
  const { result } = renderHook(() => useTodosQuery(), { wrapper })
  await waitFor(() =>
    expect(result.current.error).toEqual(new Error('Network down')),
  )
})
