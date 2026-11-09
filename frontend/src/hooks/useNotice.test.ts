import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useNotice } from './useNotice'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

it('starts without a notice and exposes a notification callback', () => {
  const { result } = renderHook(() => useNotice())
  expect(result.current.message).toBe('')
  expect(result.current.notify).toEqual(expect.any(Function))
})

it('clears the message after 4000 ms and not before', () => {
  const { result } = renderHook(() => useNotice())
  act(() => result.current.notify('Saved'))
  expect(result.current.message).toBe('Saved')
  act(() => {
    vi.advanceTimersByTime(3999)
  })
  expect(result.current.message).toBe('Saved')
  act(() => {
    vi.advanceTimersByTime(1)
  })
  expect(result.current.message).toBe('')
})

it('restarts the timer when notified again', () => {
  const { result } = renderHook(() => useNotice())
  act(() => result.current.notify('First'))
  act(() => {
    vi.advanceTimersByTime(3000)
  })
  act(() => result.current.notify('Second'))
  act(() => {
    vi.advanceTimersByTime(3000)
  })
  expect(result.current.message).toBe('Second')
  act(() => {
    vi.advanceTimersByTime(1000)
  })
  expect(result.current.message).toBe('')
})

it('restarts the timer when the same message is notified again', () => {
  const { result } = renderHook(() => useNotice())
  act(() => result.current.notify('Same'))
  act(() => {
    vi.advanceTimersByTime(3000)
  })
  act(() => result.current.notify('Same'))
  act(() => {
    vi.advanceTimersByTime(3000)
  })
  expect(result.current.message).toBe('Same')
})

it('clears the pending timeout on unmount', () => {
  const { result, unmount } = renderHook(() => useNotice())
  act(() => result.current.notify('Saved'))
  expect(vi.getTimerCount()).toBe(1)
  unmount()
  expect(vi.getTimerCount()).toBe(0)
})
