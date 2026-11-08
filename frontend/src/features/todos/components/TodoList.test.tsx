import { render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { todoFixture } from '../../../test/todoFixture'
import { TodoItem } from './TodoItem'
import { TodoList } from './TodoList'

vi.mock('../../../design-system', () => import('../../../design-system/mocks'))
vi.mock('./TodoEmptyState', () => ({
  TodoEmptyState: () => <p>Empty task list</p>,
}))
vi.mock('./TodoItem', () => ({ TodoItem: vi.fn(() => <li>Task</li>) }))

beforeEach(() => {
  vi.clearAllMocks()
})

it('shows loading feedback before showing an empty list', () => {
  const props = {
    todos: [],
    hasTodos: false,
    failed: false,
    busy: false,
    onCreate: vi.fn(),
    onToggle: vi.fn(),
    onEdit: vi.fn(),
    onDelete: vi.fn(),
  }
  const { rerender } = render(<TodoList {...props} loading />)
  expect(screen.getByRole('status')).toHaveTextContent('Loading your tasks…')
  expect(screen.queryByText('Empty task list')).not.toBeInTheDocument()
  rerender(<TodoList {...props} loading={false} />)
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  expect(screen.getByText('Empty task list')).toBeVisible()
})

const listProps = {
  hasTodos: true,
  loading: false,
  failed: false,
  busy: false,
  onCreate: vi.fn(),
  onToggle: vi.fn(),
  onEdit: vi.fn(),
  onDelete: vi.fn(),
}

it('renders one item per task', () => {
  const todos = [todoFixture, { ...todoFixture, id: 8 }]
  render(<TodoList {...listProps} todos={todos} />)
  expect(screen.getAllByRole('listitem')).toHaveLength(2)
  expect(screen.queryByText('Empty task list')).not.toBeInTheDocument()
})

it('passes the task to the toggle, edit and delete callbacks', () => {
  const todos = [todoFixture, { ...todoFixture, id: 8 }]
  render(<TodoList {...listProps} todos={todos} />)
  const items = vi.mocked(TodoItem).mock.calls
  expect(items).toHaveLength(2)
  items[1][0].onToggle()
  items[1][0].onEdit()
  items[1][0].onDelete()
  expect(listProps.onToggle).toHaveBeenCalledWith(todos[1])
  expect(listProps.onEdit).toHaveBeenCalledWith(todos[1])
  expect(listProps.onDelete).toHaveBeenCalledWith(todos[1])
})

it('shows an unavailable message when loading failed and nothing is cached', () => {
  render(<TodoList {...listProps} todos={[]} hasTodos={false} failed />)
  expect(
    screen.getByRole('heading', {
      name: 'The task list is temporarily unavailable',
    }),
  ).toBeVisible()
  expect(screen.getByText('Try again to load your tasks.')).toBeVisible()
})

it('keeps showing cached tasks when a refresh failed', () => {
  render(<TodoList {...listProps} todos={[todoFixture]} failed />)
  expect(screen.getAllByRole('listitem')).toHaveLength(1)
  expect(
    screen.queryByText('The task list is temporarily unavailable'),
  ).not.toBeInTheDocument()
})
