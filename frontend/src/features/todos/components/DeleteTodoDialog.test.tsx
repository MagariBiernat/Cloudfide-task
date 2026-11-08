import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { todoFixture } from '../../../test/todoFixture'
import { useDeleteTodoMutation } from '../hooks/useDeleteTodoMutation'
import { DeleteTodoDialog } from './DeleteTodoDialog'

vi.mock('../../../design-system', () => import('../../../design-system/mocks'))
vi.mock('../hooks/useDeleteTodoMutation', () => ({
  useDeleteTodoMutation: vi.fn(),
}))

it('shows a deletion error and allows cancelling without deleting', async () => {
  const user = userEvent.setup()
  const mutateAsync = vi.fn()
  vi.mocked(useDeleteTodoMutation).mockReturnValue({
    isPending: false,
    error: new Error('Could not delete.'),
    mutateAsync,
  } as unknown as ReturnType<typeof useDeleteTodoMutation>)
  const onClose = vi.fn()
  const onDeleted = vi.fn()
  render(
    <DeleteTodoDialog
      todo={todoFixture}
      busy={false}
      onClose={onClose}
      onDeleted={onDeleted}
    />,
  )
  expect(screen.getByRole('dialog', { name: 'Delete task?' })).toBeVisible()
  expect(
    screen.getByText(
      `The task “${todoFixture.title}” will be permanently deleted.`,
    ),
  ).toBeVisible()
  expect(screen.getByTestId('alert')).toHaveTextContent('Could not delete.')
  await user.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(onClose).toHaveBeenCalledTimes(1)
  expect(mutateAsync).not.toHaveBeenCalled()
  expect(onDeleted).not.toHaveBeenCalled()
})

function renderDialog(
  mutation: {
    isPending?: boolean
    error?: Error | null
    mutateAsync?: unknown
  },
  busy = false,
) {
  vi.mocked(useDeleteTodoMutation).mockReturnValue({
    isPending: false,
    error: null,
    mutateAsync: vi.fn(),
    ...mutation,
  } as unknown as ReturnType<typeof useDeleteTodoMutation>)
  const onClose = vi.fn()
  const onDeleted = vi.fn()
  render(
    <DeleteTodoDialog
      todo={todoFixture}
      busy={busy}
      onClose={onClose}
      onDeleted={onDeleted}
    />,
  )
  return { onClose, onDeleted }
}

it('deletes the task and reports success', async () => {
  const user = userEvent.setup()
  const mutateAsync = vi.fn().mockResolvedValue(undefined)
  const { onDeleted, onClose } = renderDialog({ mutateAsync })
  await user.click(screen.getByRole('button', { name: 'Delete task' }))
  expect(mutateAsync).toHaveBeenCalledWith(todoFixture.id)
  expect(onDeleted).toHaveBeenCalledTimes(1)
  expect(onClose).not.toHaveBeenCalled()
})

it('does not report success when deletion fails', async () => {
  const user = userEvent.setup()
  const mutateAsync = vi.fn().mockRejectedValue(new Error('nope'))
  const { onDeleted } = renderDialog({ mutateAsync })
  await user.click(screen.getByRole('button', { name: 'Delete task' }))
  expect(mutateAsync).toHaveBeenCalledTimes(1)
  expect(onDeleted).not.toHaveBeenCalled()
  expect(screen.getByRole('dialog', { name: 'Delete task?' })).toBeVisible()
})

it('disables the actions and shows progress while the deletion is pending', () => {
  renderDialog({ isPending: true })
  expect(screen.getByRole('button', { name: 'Deleting…' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Close' })).toBeDisabled()
})

it('disables the actions when the page is busy', async () => {
  const user = userEvent.setup()
  const mutateAsync = vi.fn()
  renderDialog({ mutateAsync }, true)
  const confirm = screen.getByRole('button', { name: 'Deleting…' })
  expect(confirm).toBeDisabled()
  await user.click(confirm)
  expect(mutateAsync).not.toHaveBeenCalled()
})

it('shows no error alert when there is no error', () => {
  renderDialog({})
  expect(screen.queryByTestId('alert')).not.toBeInTheDocument()
})

it('closes from the drawer close button', async () => {
  const user = userEvent.setup()
  const { onClose } = renderDialog({})
  await user.click(screen.getByRole('button', { name: 'Close' }))
  expect(onClose).toHaveBeenCalledTimes(1)
})
