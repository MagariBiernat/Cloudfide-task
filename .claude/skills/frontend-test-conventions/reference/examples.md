# Frontend examples (from the existing suite)

## API module with mocked transport

```ts
import { beforeEach, expect, it, vi } from 'vitest'
import { request } from '../../../lib/http'
import { todoFixture } from '../../../test/todoFixture'
import { todosApi } from './todos'

vi.mock('../../../lib/http', () => ({ request: vi.fn() }))
beforeEach(() => vi.clearAllMocks())

it('passes the abort signal when fetching tasks', async () => {
  const signal = new AbortController().signal
  vi.mocked(request).mockResolvedValue([todoFixture])
  await expect(todosApi.list(signal)).resolves.toEqual([todoFixture])
  expect(request).toHaveBeenCalledWith('/todos', { signal })
})
```

## Page with mocked hooks, children and design system

```tsx
vi.mock('../../design-system', () => import('../../design-system/mocks'))
vi.mock('./hooks/useTodosQuery', () => ({ useTodosQuery: vi.fn() }))
vi.mock('./components/TodoList', () => ({ TodoList: () => <p>Task list</p> }))

it('displays a query failure and resets mutation errors before retrying', async () => {
  const user = userEvent.setup()
  const refetch = vi.fn().mockResolvedValue(undefined)
  vi.mocked(useTodosQuery).mockReturnValue({
    data: [], isPending: false, isFetching: false, isError: true,
    error: new Error('The server is unavailable.'), refetch,
  } as unknown as ReturnType<typeof useTodosQuery>)
  render(<TodosPage />)
  expect(screen.getByTestId('alert')).toHaveTextContent('The server is unavailable.')
  await user.click(screen.getByRole('button', { name: 'Try again' }))
  await waitFor(() => expect(refetch).toHaveBeenCalledTimes(1))
})
```

## React Query mutation hook (pattern, not yet in the suite)

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { expect, it, vi } from 'vitest'
import { todoFixture } from '../../../test/todoFixture'
import { todoKeys } from '../api/queryKeys'
import { todosApi } from '../api/todos'
import { useCreateTodoMutation } from './useCreateTodoMutation'

vi.mock('../api/todos', () => ({ todosApi: { create: vi.fn() } }))

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return { client, ...renderHook(() => useCreateTodoMutation(), { wrapper }) }
}

it('puts the saved task first and removes a stale copy with the same id', async () => {
  const saved = { ...todoFixture, title: 'Saved' }
  vi.mocked(todosApi.create).mockResolvedValue(saved)
  const { client, result } = setup()
  client.setQueryData(todoKeys.list, [{ ...todoFixture, id: 1 }, todoFixture])
  await act(() => result.current.mutateAsync(todoFixture))
  expect(client.getQueryData(todoKeys.list)).toEqual([saved, { ...todoFixture, id: 1 }])
})
```
