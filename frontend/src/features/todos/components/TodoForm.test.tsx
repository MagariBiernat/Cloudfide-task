import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { TodoForm } from './TodoForm'
import type { TodoInput } from '../types'

vi.mock('../../../design-system', () => import('../../../design-system/mocks'))

describe('TodoForm', () => {
  it('rejects a whitespace-only title without submitting', async () => {
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    render(
      <TodoForm
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        busy={false}
        error={null}
      />,
    )
    await user.type(screen.getByLabelText(/Task title/), '   ')
    await user.click(screen.getByRole('button', { name: 'Save task' }))
    expect(screen.getByText('Enter a task title.')).toBeVisible()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('submits trimmed values and the selected priority', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    const user = userEvent.setup()
    render(
      <TodoForm
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        busy={false}
        error={null}
      />,
    )
    await user.type(screen.getByLabelText(/Task title/), '  Prepare a demo  ')
    await user.selectOptions(screen.getByLabelText('Priority'), 'high')
    await user.click(screen.getByRole('button', { name: 'Save task' }))
    expect(onSubmit).toHaveBeenCalledWith({
      title: 'Prepare a demo',
      description: '',
      priority: 'high',
      due_date: null,
      completed: false,
    })
  })

  it('submits the typed description trimmed', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    const user = userEvent.setup()
    renderForm(onSubmit)
    await user.type(screen.getByLabelText(/Task title/), 'Task')
    await user.type(screen.getByLabelText(/Description/), '  Some details  ')
    await user.click(screen.getByRole('button', { name: 'Save task' }))
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Task', description: 'Some details' }),
    )
  })

  it('submits the selected due date as YYYY-MM-DD', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    const user = userEvent.setup()
    renderForm(onSubmit)
    await user.type(screen.getByLabelText(/Task title/), 'Task')
    await user.type(screen.getByLabelText(/Due date/), '2026-03-05')
    await user.click(screen.getByRole('button', { name: 'Save task' }))
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ due_date: '2026-03-05' }),
    )
  })

  it('submits null after the due date is cleared', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    const user = userEvent.setup()
    renderForm(onSubmit, {
      title: 'Task',
      description: '',
      priority: 'medium',
      due_date: '2026-03-05',
      completed: false,
    })
    await user.clear(screen.getByLabelText(/Due date/))
    await user.click(screen.getByRole('button', { name: 'Save task' }))
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ due_date: null }),
    )
  })

  it('shows an error and does not submit a description over 2000 characters', async () => {
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    renderForm(onSubmit)
    await user.type(screen.getByLabelText(/Task title/), 'Task')
    await user.click(screen.getByLabelText(/Description/))
    await user.paste('a'.repeat(2001))
    await user.click(screen.getByRole('button', { name: 'Save task' }))
    expect(
      screen.getByText('The description must be at most 2000 characters.'),
    ).toBeVisible()
    expect(onSubmit).not.toHaveBeenCalled()
  })
})

function renderForm(
  onSubmit: (todo: TodoInput) => Promise<void>,
  initial?: TodoInput,
) {
  render(
    <TodoForm
      initial={initial}
      onSubmit={onSubmit}
      onCancel={vi.fn()}
      busy={false}
      error={null}
    />,
  )
}
