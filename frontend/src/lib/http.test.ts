import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { request } from './http'

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

it('prefixes the path with /api and sends JSON headers', async () => {
  fetchMock.mockResolvedValue(new Response('{}', { status: 200 }))
  await request('/todos', { method: 'POST', body: '{"a":1}' })
  expect(fetchMock).toHaveBeenCalledWith('/api/todos', {
    method: 'POST',
    body: '{"a":1}',
    headers: { 'Content-Type': 'application/json' },
  })
})

it('lets callers add and override headers', async () => {
  fetchMock.mockResolvedValue(new Response('{}', { status: 200 }))
  await request('/todos', {
    headers: { 'Content-Type': 'text/plain', 'X-Test': '1' },
  })
  expect(fetchMock.mock.calls[0][1].headers).toEqual({
    'Content-Type': 'text/plain',
    'X-Test': '1',
  })
})

it('returns the parsed JSON body on success', async () => {
  fetchMock.mockResolvedValue(
    new Response(JSON.stringify([{ id: 1 }]), { status: 200 }),
  )
  await expect(request('/todos')).resolves.toEqual([{ id: 1 }])
})

it('returns undefined for 204 responses', async () => {
  fetchMock.mockResolvedValue(new Response(null, { status: 204 }))
  await expect(
    request('/todos/1', { method: 'DELETE' }),
  ).resolves.toBeUndefined()
})

it('reports a friendly message when the network fails', async () => {
  fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
  await expect(request('/todos')).rejects.toThrow(
    'Cannot connect to the server. Please try again.',
  )
})

it('rethrows the original error when the request was aborted', async () => {
  const controller = new AbortController()
  controller.abort()
  const abortError = new DOMException('Aborted', 'AbortError')
  fetchMock.mockRejectedValue(abortError)
  await expect(request('/todos', { signal: controller.signal })).rejects.toBe(
    abortError,
  )
})

it('shows a validation hint for 422 responses regardless of the body', async () => {
  fetchMock.mockResolvedValue(
    new Response(JSON.stringify({ detail: 'ignored' }), { status: 422 }),
  )
  await expect(request('/todos')).rejects.toThrow(/Check the task details/)
})

it('uses a string detail from an error response', async () => {
  fetchMock.mockResolvedValue(
    new Response(JSON.stringify({ detail: 'Task not found.' }), {
      status: 404,
    }),
  )
  await expect(request('/todos/9')).rejects.toThrow('Task not found.')
})

it('falls back to a generic message when detail is not a string', async () => {
  fetchMock.mockResolvedValue(
    new Response(JSON.stringify({ detail: [{ msg: 'x' }] }), { status: 400 }),
  )
  await expect(request('/todos')).rejects.toThrow(
    'The operation failed. Please try again.',
  )
})

it('falls back to a generic message for a non-JSON error body', async () => {
  fetchMock.mockResolvedValue(
    new Response('<html>oops</html>', { status: 500 }),
  )
  await expect(request('/todos')).rejects.toThrow(
    'The operation failed. Please try again.',
  )
})
