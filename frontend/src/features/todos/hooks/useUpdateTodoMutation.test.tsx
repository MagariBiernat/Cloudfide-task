import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, expect, it, vi } from 'vitest'
import { todoFixture } from '../../../test/todoFixture'
import { todoKeys } from '../api/queryKeys'
import { todosApi } from '../api/todos'
import { useUpdateTodoMutation } from './useUpdateTodoMutation'

vi.mock('../api/todos', () => ({ todosApi: { update: vi.fn() } }))

let client: QueryClient
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={client}>{children}</QueryClientProvider>
)

beforeEach(() => {
  vi.clearAllMocks()
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
})

it('calls the API and replaces only the matching task in the cached list', async () => {
  const saved = { ...todoFixture, completed: true }
  const other = { ...todoFixture, id: 8 }
  vi.mocked(todosApi.update).mockResolvedValue(saved)
  client.setQueryData(todoKeys.list, [other, todoFixture])
  const { result } = renderHook(() => useUpdateTodoMutation(), { wrapper })
  await act(() =>
    result.current.mutateAsync({
      id: todoFixture.id,
      input: { completed: true },
    }),
  )
  expect(todosApi.update).toHaveBeenCalledWith(todoFixture.id, {
    completed: true,
  })
  expect(client.getQueryData(todoKeys.list)).toEqual([other, saved])
})

it('does not create a list cache when none exists', async () => {
  vi.mocked(todosApi.update).mockResolvedValue(todoFixture)
  const { result } = renderHook(() => useUpdateTodoMutation(), { wrapper })
  await act(() =>
    result.current.mutateAsync({ id: todoFixture.id, input: { title: 'x' } }),
  )
  expect(client.getQueryData(todoKeys.list)).toBeUndefined()
})

it('keeps the cached list when the API fails', async () => {
  vi.mocked(todosApi.update).mockRejectedValue(new Error('Boom'))
  client.setQueryData(todoKeys.list, [todoFixture])
  const { result } = renderHook(() => useUpdateTodoMutation(), { wrapper })
  await act(() =>
    expect(
      result.current.mutateAsync({ id: todoFixture.id, input: {} }),
    ).rejects.toThrow('Boom'),
  )
  expect(client.getQueryData(todoKeys.list)).toEqual([todoFixture])
})
