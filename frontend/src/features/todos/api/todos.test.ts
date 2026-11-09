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

it('sends only writable task fields on update with PATCH', async () => {
  vi.mocked(request).mockResolvedValue(todoFixture)
  await expect(todosApi.update(7, todoFixture)).resolves.toEqual(todoFixture)
  expect(request).toHaveBeenCalledWith('/todos/7', {
    method: 'PATCH',
    body: JSON.stringify({
      title: todoFixture.title,
      description: '',
      priority: 'medium',
      due_date: null,
      completed: false,
    }),
  })
  const body = JSON.parse(vi.mocked(request).mock.calls[0][1]!.body as string)
  expect(body).not.toHaveProperty('id')
  expect(body).not.toHaveProperty('created_at')
  expect(body).not.toHaveProperty('updated_at')
})

it('omits fields not provided in a partial update', async () => {
  vi.mocked(request).mockResolvedValue(todoFixture)
  await todosApi.update(3, { completed: true })
  const body = JSON.parse(vi.mocked(request).mock.calls[0][1]!.body as string)
  expect(body).toEqual({ completed: true })
})

it('deletes a task with DELETE', async () => {
  vi.mocked(request).mockResolvedValue(undefined)
  await expect(todosApi.remove(9)).resolves.toBeUndefined()
  expect(request).toHaveBeenCalledWith('/todos/9', { method: 'DELETE' })
})

it('sends only writable task fields on creation', async () => {
  vi.mocked(request).mockResolvedValue(todoFixture)
  await expect(todosApi.create(todoFixture)).resolves.toEqual(todoFixture)
  expect(request).toHaveBeenCalledWith('/todos', {
    method: 'POST',
    body: JSON.stringify({
      title: todoFixture.title,
      description: '',
      priority: 'medium',
      due_date: null,
      completed: false,
    }),
  })
})
