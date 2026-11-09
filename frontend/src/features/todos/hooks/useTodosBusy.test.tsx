import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, expect, it, vi } from 'vitest'
import { todosApi } from '../api/todos'
import { todoFixture } from '../../../test/todoFixture'
import type { Todo, TodoInput } from '../types'
import { useCreateTodoMutation } from './useCreateTodoMutation'
import { useTodosBusy } from './useTodosBusy'

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

it('is false when no mutation is running', () => {
  const { result } = renderHook(() => useTodosBusy(), { wrapper })
  expect(result.current).toBe(false)
})

it('is true while a todo mutation is in flight and false once it settles', async () => {
  let resolve!: (todo: Todo) => void
  vi.mocked(todosApi.create).mockReturnValue(
    new Promise<Todo>((r) => {
      resolve = r
    }),
  )
  const { result } = renderHook(
    () => ({ busy: useTodosBusy(), create: useCreateTodoMutation() }),
    { wrapper },
  )
  let pending!: Promise<Todo>
  act(() => {
    pending = result.current.create.mutateAsync(input)
  })
  await waitFor(() => expect(result.current.busy).toBe(true))
  await act(async () => {
    resolve(todoFixture)
    await pending
  })
  await waitFor(() => expect(result.current.busy).toBe(false))
})
