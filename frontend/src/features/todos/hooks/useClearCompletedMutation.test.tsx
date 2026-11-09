import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, expect, it, vi } from 'vitest'
import { todoFixture } from '../../../test/todoFixture'
import { todoKeys } from '../api/queryKeys'
import { todosApi } from '../api/todos'
import { useClearCompletedMutation } from './useClearCompletedMutation'

vi.mock('../api/todos', () => ({ todosApi: { clearCompleted: vi.fn() } }))

beforeEach(() => vi.clearAllMocks())

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  const { result } = renderHook(() => useClearCompletedMutation(), { wrapper })
  return { client, result }
}

it('calls the API and returns the deleted count', async () => {
  vi.mocked(todosApi.clearCompleted).mockResolvedValue({ deleted: 2 })
  const { result } = setup()
  let data
  await act(async () => {
    data = await result.current.mutateAsync()
  })
  expect(todosApi.clearCompleted).toHaveBeenCalledTimes(1)
  expect(data).toEqual({ deleted: 2 })
})

it('removes completed todos from the cached list and keeps active ones', async () => {
  vi.mocked(todosApi.clearCompleted).mockResolvedValue({ deleted: 1 })
  const { client, result } = setup()
  const active = { ...todoFixture, id: 1, completed: false }
  const done = { ...todoFixture, id: 2, completed: true }
  client.setQueryData(todoKeys.list, [active, done])
  await act(() => result.current.mutateAsync())
  expect(client.getQueryData(todoKeys.list)).toEqual([active])
})

it('leaves the cache undefined when nothing is cached', async () => {
  vi.mocked(todosApi.clearCompleted).mockResolvedValue({ deleted: 0 })
  const { client, result } = setup()
  await act(() => result.current.mutateAsync())
  expect(client.getQueryData(todoKeys.list)).toBeUndefined()
})

it('keeps the cache unchanged and surfaces the error when the API fails', async () => {
  vi.mocked(todosApi.clearCompleted).mockRejectedValue(new Error('boom'))
  const { client, result } = setup()
  const list = [
    { ...todoFixture, id: 1, completed: false },
    { ...todoFixture, id: 2, completed: true },
  ]
  client.setQueryData(todoKeys.list, list)
  await act(async () => {
    await expect(result.current.mutateAsync()).rejects.toThrow('boom')
  })
  expect(client.getQueryData(todoKeys.list)).toEqual(list)
  await waitFor(() => expect(result.current.error).toEqual(new Error('boom')))
})
