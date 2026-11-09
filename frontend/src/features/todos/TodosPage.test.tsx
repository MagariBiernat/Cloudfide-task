import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { todoFixture } from '../../test/todoFixture'
import { useNotice } from '../../hooks/useNotice'
import { useClearCompletedMutation } from './hooks/useClearCompletedMutation'
import { useTodoFilters } from './hooks/useTodoFilters'
import { useTodosBusy } from './hooks/useTodosBusy'
import { useTodosQuery } from './hooks/useTodosQuery'
import { useUpdateTodoMutation } from './hooks/useUpdateTodoMutation'
import { TodosPage } from './TodosPage'

vi.mock('../../design-system', () => import('../../design-system/mocks'))
vi.mock('../../hooks/useNotice', () => ({ useNotice: vi.fn() }))
vi.mock('./hooks/useClearCompletedMutation', () => ({
  useClearCompletedMutation: vi.fn(),
}))
vi.mock('./hooks/useTodoFilters', () => ({ useTodoFilters: vi.fn() }))
vi.mock('./hooks/useTodosBusy', () => ({ useTodosBusy: vi.fn() }))
vi.mock('./hooks/useTodosQuery', () => ({ useTodosQuery: vi.fn() }))
vi.mock('./hooks/useUpdateTodoMutation', () => ({
  useUpdateTodoMutation: vi.fn(),
}))
vi.mock('./components/TodosHeader', () => ({
  TodosHeader: ({
    onCreate,
    onClearCompleted,
    completedCount,
  }: {
    onCreate: () => void
    onClearCompleted: () => void
    completedCount: number
  }) => (
    <>
      <h1>Tasks</h1>
      <p>Completed count: {completedCount}</p>
      <button onClick={onCreate}>Header create</button>
      <button onClick={onClearCompleted}>Header clear</button>
    </>
  ),
}))
vi.mock('./components/TodoFilters', () => ({ TodoFilters: () => null }))
vi.mock('./components/TodoList', () => ({
  TodoList: (props: {
    todos: { id: number }[]
    onCreate: () => void
    onToggle: (todo: unknown) => void
    onEdit: (todo: unknown) => void
    onDelete: (todo: unknown) => void
  }) => (
    <>
      <p>Task list</p>
      <button onClick={props.onCreate}>List create</button>
      <button onClick={() => props.onToggle(props.todos[0])}>Toggle</button>
      <button onClick={() => props.onEdit(props.todos[0])}>Edit</button>
      <button onClick={() => props.onDelete(props.todos[0])}>Delete</button>
    </>
  ),
}))
vi.mock('./components/TodoEditor', () => ({
  TodoEditor: (props: {
    todo: { id: number } | 'new'
    onClose: () => void
    onSaved: (notice: string) => void
  }) => (
    <div>
      <p>
        Editor for {props.todo === 'new' ? 'new task' : `task ${props.todo.id}`}
      </p>
      <button onClick={props.onClose}>Close editor</button>
      <button onClick={() => props.onSaved('Task saved.')}>Save editor</button>
    </div>
  ),
}))
vi.mock('./components/DeleteTodoDialog', () => ({
  DeleteTodoDialog: (props: {
    todo: { id: number }
    onClose: () => void
    onDeleted: () => void
  }) => (
    <div>
      <p>Deleting task {props.todo.id}</p>
      <button onClick={props.onClose}>Close delete</button>
      <button onClick={props.onDeleted}>Confirm delete</button>
    </div>
  ),
}))
vi.mock('../../components/SuccessNotice', () => ({
  SuccessNotice: ({ message }: { message: string }) =>
    message ? <p role="status">{message}</p> : null,
}))

const notify = vi.fn()

function setup({
  busy = false,
  mutateAsync = vi.fn(),
  mutationError = null as Error | null,
  message = '',
} = {}) {
  vi.mocked(useTodosQuery).mockReturnValue({
    data: [todoFixture],
    isPending: false,
    isFetching: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof useTodosQuery>)
  vi.mocked(useUpdateTodoMutation).mockReturnValue({
    error: mutationError,
    reset: vi.fn(),
    mutateAsync,
  } as unknown as ReturnType<typeof useUpdateTodoMutation>)
  vi.mocked(useTodosBusy).mockReturnValue(busy)
  vi.mocked(useNotice).mockReturnValue({ message, notify })
  vi.mocked(useTodoFilters).mockReturnValue({
    filter: 'all',
    search: '',
    sort: 'newest',
    visible: [todoFixture],
    setFilter: vi.fn(),
    setSearch: vi.fn(),
    setSort: vi.fn(),
  })
  return { mutateAsync }
}

function mockClear({
  mutateAsync = vi.fn(),
  reset = vi.fn(),
  error = null as Error | null,
} = {}) {
  vi.mocked(useClearCompletedMutation).mockReturnValue({
    mutateAsync,
    reset,
    error,
  } as unknown as ReturnType<typeof useClearCompletedMutation>)
  return { mutateAsync, reset }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockClear()
})

it('displays a query failure and resets mutation errors before retrying', async () => {
  const user = userEvent.setup()
  const refetch = vi.fn().mockResolvedValue(undefined)
  const reset = vi.fn()
  vi.mocked(useTodosQuery).mockReturnValue({
    data: [],
    isPending: false,
    isFetching: false,
    isError: true,
    error: new Error('The server is unavailable.'),
    refetch,
  } as unknown as ReturnType<typeof useTodosQuery>)
  vi.mocked(useUpdateTodoMutation).mockReturnValue({
    error: null,
    reset,
    mutateAsync: vi.fn(),
  } as unknown as ReturnType<typeof useUpdateTodoMutation>)
  vi.mocked(useTodosBusy).mockReturnValue(false)
  vi.mocked(useNotice).mockReturnValue({ message: '', notify: vi.fn() })
  vi.mocked(useTodoFilters).mockReturnValue({
    filter: 'all',
    search: '',
    sort: 'newest',
    visible: [],
    setFilter: vi.fn(),
    setSearch: vi.fn(),
    setSort: vi.fn(),
  })
  render(<TodosPage />)
  expect(screen.getByTestId('alert')).toHaveTextContent(
    'The server is unavailable.',
  )
  await user.click(screen.getByRole('button', { name: 'Try again' }))
  await waitFor(() => expect(refetch).toHaveBeenCalledTimes(1))
  expect(reset).toHaveBeenCalledTimes(1)
  expect(reset.mock.invocationCallOrder[0]).toBeLessThan(
    refetch.mock.invocationCallOrder[0],
  )
})

it('marks an active task complete and announces it', async () => {
  const user = userEvent.setup()
  const { mutateAsync } = setup({
    mutateAsync: vi.fn().mockResolvedValue({ ...todoFixture, completed: true }),
  })
  render(<TodosPage />)
  await user.click(screen.getByRole('button', { name: 'Toggle' }))
  expect(mutateAsync).toHaveBeenCalledWith({
    id: todoFixture.id,
    input: { completed: true },
  })
  expect(notify).toHaveBeenCalledWith('Another task complete. Well done!')
})

it('marks a completed task as active and announces it', async () => {
  const user = userEvent.setup()
  const { mutateAsync } = setup({
    mutateAsync: vi
      .fn()
      .mockResolvedValue({ ...todoFixture, completed: false }),
  })
  vi.mocked(useTodoFilters).mockReturnValue({
    filter: 'all',
    search: '',
    sort: 'newest',
    visible: [{ ...todoFixture, completed: true }],
    setFilter: vi.fn(),
    setSearch: vi.fn(),
    setSort: vi.fn(),
  })
  render(<TodosPage />)
  await user.click(screen.getByRole('button', { name: 'Toggle' }))
  expect(mutateAsync).toHaveBeenCalledWith({
    id: todoFixture.id,
    input: { completed: false },
  })
  expect(notify).toHaveBeenCalledWith('Task marked as active.')
})

it('does not toggle while busy', async () => {
  const user = userEvent.setup()
  const { mutateAsync } = setup({ busy: true })
  render(<TodosPage />)
  await user.click(screen.getByRole('button', { name: 'Toggle' }))
  expect(mutateAsync).not.toHaveBeenCalled()
  expect(notify).not.toHaveBeenCalled()
})

it('swallows a failed toggle without announcing success', async () => {
  const user = userEvent.setup()
  const mutateAsync = vi.fn().mockRejectedValue(new Error('nope'))
  setup({ mutateAsync })
  render(<TodosPage />)
  await user.click(screen.getByRole('button', { name: 'Toggle' }))
  await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1))
  expect(notify).not.toHaveBeenCalled()
})

it('displays a mutation error in the alert', () => {
  setup({ mutationError: new Error('Could not update.') })
  render(<TodosPage />)
  expect(screen.getByTestId('alert')).toHaveTextContent('Could not update.')
})

it('opens the editor for a new task from the header and the list', async () => {
  const user = userEvent.setup()
  setup()
  render(<TodosPage />)
  expect(screen.queryByText('Editor for new task')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Header create' }))
  expect(screen.getByText('Editor for new task')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Close editor' }))
  expect(screen.queryByText('Editor for new task')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'List create' }))
  expect(screen.getByText('Editor for new task')).toBeVisible()
})

it('opens the editor for an existing task and closes it after saving with a notice', async () => {
  const user = userEvent.setup()
  setup()
  render(<TodosPage />)
  await user.click(screen.getByRole('button', { name: 'Edit' }))
  expect(screen.getByText(`Editor for task ${todoFixture.id}`)).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Save editor' }))
  expect(notify).toHaveBeenCalledWith('Task saved.')
  expect(screen.queryByText(/Editor for/)).not.toBeInTheDocument()
})

it('opens the delete dialog, can cancel it, and announces a deletion', async () => {
  const user = userEvent.setup()
  setup()
  render(<TodosPage />)
  await user.click(screen.getByRole('button', { name: 'Delete' }))
  expect(screen.getByText(`Deleting task ${todoFixture.id}`)).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Close delete' }))
  expect(screen.queryByText(/Deleting task/)).not.toBeInTheDocument()
  expect(notify).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Delete' }))
  await user.click(screen.getByRole('button', { name: 'Confirm delete' }))
  expect(notify).toHaveBeenCalledWith('Task deleted.')
  expect(screen.queryByText(/Deleting task/)).not.toBeInTheDocument()
})

it('clears completed tasks and announces how many were removed', async () => {
  const user = userEvent.setup()
  setup()
  const { mutateAsync } = mockClear({
    mutateAsync: vi.fn().mockResolvedValue({ deleted: 2 }),
  })
  render(<TodosPage />)
  await user.click(screen.getByRole('button', { name: 'Header clear' }))
  expect(mutateAsync).toHaveBeenCalledTimes(1)
  expect(notify).toHaveBeenCalledWith('2 completed task(s) cleared.')
})

it('does not clear completed tasks while busy', async () => {
  const user = userEvent.setup()
  setup({ busy: true })
  const { mutateAsync } = mockClear()
  render(<TodosPage />)
  await user.click(screen.getByRole('button', { name: 'Header clear' }))
  expect(mutateAsync).not.toHaveBeenCalled()
  expect(notify).not.toHaveBeenCalled()
})

it('does not announce success when clearing completed tasks fails', async () => {
  const user = userEvent.setup()
  setup()
  const { mutateAsync } = mockClear({
    mutateAsync: vi.fn().mockRejectedValue(new Error('nope')),
  })
  render(<TodosPage />)
  await user.click(screen.getByRole('button', { name: 'Header clear' }))
  await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1))
  expect(notify).not.toHaveBeenCalled()
})

it('displays the clear error and resets all errors before refetching on retry', async () => {
  const user = userEvent.setup()
  setup({ mutationError: new Error('Could not update.') })
  const { reset } = mockClear({ error: new Error('Could not clear.') })
  const refetch = vi.fn().mockResolvedValue(undefined)
  vi.mocked(useTodosQuery).mockReturnValue({
    data: [todoFixture],
    isPending: false,
    isFetching: false,
    isError: false,
    error: null,
    refetch,
  } as unknown as ReturnType<typeof useTodosQuery>)
  const toggleReset = vi.fn()
  vi.mocked(useUpdateTodoMutation).mockReturnValue({
    error: new Error('Could not update.'),
    reset: toggleReset,
    mutateAsync: vi.fn(),
  } as unknown as ReturnType<typeof useUpdateTodoMutation>)
  render(<TodosPage />)
  expect(screen.getByTestId('alert')).toHaveTextContent('Could not clear.')
  await user.click(screen.getByRole('button', { name: 'Try again' }))
  await waitFor(() => expect(refetch).toHaveBeenCalledTimes(1))
  expect(reset).toHaveBeenCalledTimes(1)
  expect(toggleReset).toHaveBeenCalledTimes(1)
})

it('passes the number of completed tasks to the header', () => {
  setup()
  vi.mocked(useTodosQuery).mockReturnValue({
    data: [
      todoFixture,
      { ...todoFixture, id: 2, completed: true },
      { ...todoFixture, id: 3, completed: true },
    ],
    isPending: false,
    isFetching: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof useTodosQuery>)
  render(<TodosPage />)
  expect(screen.getByText('Completed count: 2')).toBeVisible()
})

it('renders the success notice message', () => {
  setup({ message: 'Task deleted.' })
  render(<TodosPage />)
  expect(screen.getByRole('status')).toHaveTextContent('Task deleted.')
})
