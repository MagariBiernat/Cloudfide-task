import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { TodosHeader } from './TodosHeader'

vi.mock('../../../design-system', () => import('../../../design-system/mocks'))

it('invokes creation when enabled and blocks it when disabled', async () => {
  const user = userEvent.setup()
  const onCreate = vi.fn()
  const { rerender } = render(
    <TodosHeader disabled={false} onCreate={onCreate} />,
  )
  expect(screen.getByRole('heading', { name: 'Tasks' })).toBeVisible()
  expect(
    screen.getByText('Create, organize, and complete tasks.'),
  ).toBeVisible()
  const button = screen.getByRole('button', { name: 'New task' })
  await user.click(button)
  expect(onCreate).toHaveBeenCalledTimes(1)
  rerender(<TodosHeader disabled onCreate={onCreate} />)
  expect(button).toBeDisabled()
  await user.click(button)
  expect(onCreate).toHaveBeenCalledTimes(1)
})

it('hides the clear button when no tasks are completed', () => {
  render(
    <TodosHeader
      disabled={false}
      completedCount={0}
      onCreate={vi.fn()}
      onClearCompleted={vi.fn()}
    />,
  )
  expect(screen.queryByRole('button', { name: /Clear completed/ })).toBeNull()
})

it('hides the clear button when no handler is given', () => {
  render(<TodosHeader disabled={false} completedCount={2} onCreate={vi.fn()} />)
  expect(screen.queryByRole('button', { name: /Clear completed/ })).toBeNull()
})

it('shows the clear button with the count and calls the handler on click', async () => {
  const user = userEvent.setup()
  const onClearCompleted = vi.fn()
  render(
    <TodosHeader
      disabled={false}
      completedCount={3}
      onCreate={vi.fn()}
      onClearCompleted={onClearCompleted}
    />,
  )
  await user.click(screen.getByRole('button', { name: 'Clear completed (3)' }))
  expect(onClearCompleted).toHaveBeenCalledTimes(1)
})

it('disables the clear button when the header is disabled', async () => {
  const user = userEvent.setup()
  const onClearCompleted = vi.fn()
  render(
    <TodosHeader
      disabled
      completedCount={1}
      onCreate={vi.fn()}
      onClearCompleted={onClearCompleted}
    />,
  )
  const button = screen.getByRole('button', { name: 'Clear completed (1)' })
  expect(button).toBeDisabled()
  await user.click(button)
  expect(onClearCompleted).not.toHaveBeenCalled()
})
