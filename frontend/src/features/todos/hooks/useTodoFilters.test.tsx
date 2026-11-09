import { act, renderHook } from '@testing-library/react'
import { expect, it } from 'vitest'
import { todoFixture } from '../../../test/todoFixture'
import { useTodoFilters } from './useTodoFilters'

const active = {
  ...todoFixture,
  id: 1,
  title: 'Buy milk',
  created_at: '2026-10-01T12:00:00Z',
}
const done = {
  ...todoFixture,
  id: 2,
  title: 'Write report',
  completed: true,
  priority: 'high' as const,
  created_at: '2026-10-02T12:00:00Z',
}
const todos = [active, done]

it('starts with all tasks, empty search and newest sort', () => {
  const { result } = renderHook(() => useTodoFilters(todos))
  expect(result.current.filter).toBe('all')
  expect(result.current.search).toBe('')
  expect(result.current.sort).toBe('newest')
  expect(result.current.visible).toEqual([done, active])
})

it('narrows visible tasks when the filter changes', () => {
  const { result } = renderHook(() => useTodoFilters(todos))
  act(() => result.current.setFilter('completed'))
  expect(result.current.visible).toEqual([done])
  act(() => result.current.setFilter('active'))
  expect(result.current.visible).toEqual([active])
})

it('narrows visible tasks when the search changes', () => {
  const { result } = renderHook(() => useTodoFilters(todos))
  act(() => result.current.setSearch('MILK'))
  expect(result.current.search).toBe('MILK')
  expect(result.current.visible).toEqual([active])
})

it('reorders visible tasks when the sort changes', () => {
  const { result } = renderHook(() => useTodoFilters(todos))
  act(() => result.current.setSort('priority'))
  expect(result.current.sort).toBe('priority')
  expect(result.current.visible).toEqual([done, active])
  act(() => result.current.setSort('due'))
  expect(result.current.visible).toEqual([done, active])
})
