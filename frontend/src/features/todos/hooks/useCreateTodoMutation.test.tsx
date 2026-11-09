import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, expect, it, vi } from 'vitest'
import { todoKeys } from '../api/queryKeys'
import { todosApi } from '../api/todos'
import { todoFixture } from '../../../test/todoFixture'
import type { TodoInput } from '../types'
import { useCreateTodoMutation } from './useCreateTodoMutation'

vi.mock('../api/todos', () => ({ todosApi: { create: vi.fn() } }))

const input: TodoInput = {
  title: 'New',
  description: '',
  priority: 'low',
  due_date: null,
  completed: false,
}

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

it('calls the API with the input and prepends the saved task', async () => {
  const saved = { ...todoFixture, id: 8, title: 'New' }
  vi.mocked(todosApi.create).mockResolvedValue(saved)
  client.setQueryData(todoKeys.list, [todoFixture])
  const { result } = renderHook(() => useCreateTodoMutation(), { wrapper })
  await act(() => result.current.mutateAsync(input))
  expect(todosApi.create).toHaveBeenCalledWith(input)
  expect(client.getQueryData(todoKeys.list)).toEqual([saved, todoFixture])
})

it('replaces an existing entry with the same id without duplicating it', async () => {
  const other = { ...todoFixture, id: 1 }
  const saved = { ...todoFixture, title: 'Updated' }
  vi.mocked(todosApi.create).mockResolvedValue(saved)
  client.setQueryData(todoKeys.list, [other, todoFixture])
  const { result } = renderHook(() => useCreateTodoMutation(), { wrapper })
  await act(() => result.current.mutateAsync(input))
  expect(client.getQueryData(todoKeys.list)).toEqual([saved, other])
})

it('creates the list when the cache is empty', async () => {
  vi.mocked(todosApi.create).mockResolvedValue(todoFixture)
  const { result } = renderHook(() => useCreateTodoMutation(), { wrapper })
  await act(() => result.current.mutateAsync(input))
  expect(client.getQueryData(todoKeys.list)).toEqual([todoFixture])
})
