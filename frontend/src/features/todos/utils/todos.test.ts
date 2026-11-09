import { afterEach, describe, expect, it, vi } from 'vitest'
import { formatDate, isOverdue, selectTodos, validateTodo } from './todos'
import type { TodoInput } from '../types'
import type { Todo } from '../types'

const base: Todo = {
  id: 1,
  title: 'Sprint plan',
  description: '',
  priority: 'medium',
  completed: false,
  due_date: null,
  created_at: '2026-10-01T12:00:00Z',
  updated_at: '2026-10-01T12:00:00Z',
}

describe('selectTodos', () => {
  it('combines status with a case-insensitive search in the description', () => {
    const matching = { ...base, description: 'Discuss the API' }
    const todos = [
      matching,
      { ...matching, id: 2, completed: true },
      { ...base, id: 3 },
    ]
    expect(selectTodos(todos, 'active', ' api ', 'newest')).toEqual([matching])
  })

  it('sorts by priority without changing the source array', () => {
    const high: Todo = { ...base, id: 2, priority: 'high' }
    const todos = [base, high]
    expect(selectTodos(todos, 'all', '', 'priority')).toEqual([high, base])
    expect(todos).toEqual([base, high])
  })

  it('sorts by due date with missing dates last and higher id first on ties', () => {
    const none = { ...base, id: 1, due_date: null }
    const later = { ...base, id: 2, due_date: '2026-12-01' }
    const earlyLowId = { ...base, id: 3, due_date: '2026-11-01' }
    const earlyHighId = { ...base, id: 4, due_date: '2026-11-01' }
    const noneHighId = { ...base, id: 5, due_date: null }
    expect(
      selectTodos(
        [none, later, earlyLowId, noneHighId, earlyHighId],
        'all',
        '',
        'due',
      ),
    ).toEqual([earlyHighId, earlyLowId, later, noneHighId, none])
  })

  it('sorts newest first by creation time with higher id first on ties', () => {
    const old = { ...base, id: 1, created_at: '2026-09-01T10:00:00Z' }
    const newer = { ...base, id: 2, created_at: '2026-10-01T10:00:00Z' }
    const tieLow = { ...base, id: 3, created_at: '2026-08-01T10:00:00Z' }
    const tieHigh = { ...base, id: 4, created_at: '2026-08-01T10:00:00Z' }
    expect(
      selectTodos([tieLow, old, tieHigh, newer], 'all', '', 'newest'),
    ).toEqual([newer, old, tieHigh, tieLow])
  })

  it('keeps only completed tasks for the completed filter', () => {
    const done = { ...base, id: 2, completed: true }
    expect(selectTodos([base, done], 'completed', '', 'newest')).toEqual([done])
  })
})

describe('validateTodo', () => {
  const valid: TodoInput = {
    title: 'Task',
    description: '',
    priority: 'medium',
    due_date: null,
    completed: false,
  }

  it('returns no errors for valid input', () => {
    expect(validateTodo({ ...valid, due_date: '2026-02-28' })).toEqual({})
  })

  it.each(['', '   '])('rejects an empty title %j', (title) => {
    expect(validateTodo({ ...valid, title })).toEqual({
      title: 'Enter a task title.',
    })
  })

  it('rejects a title longer than 120 characters after trimming', () => {
    expect(validateTodo({ ...valid, title: 'a'.repeat(121) })).toEqual({
      title: 'The title must be at most 120 characters.',
    })
    expect(validateTodo({ ...valid, title: ` ${'a'.repeat(120)} ` })).toEqual(
      {},
    )
  })

  it('rejects a description longer than 2000 characters after trimming', () => {
    expect(validateTodo({ ...valid, description: 'a'.repeat(2001) })).toEqual({
      description: 'The description must be at most 2000 characters.',
    })
    expect(
      validateTodo({ ...valid, description: ` ${'a'.repeat(2000)} ` }),
    ).toEqual({})
  })

  it.each(['03/05/2026', '2026-3-5', 'tomorrow', '2026-02-30', '2026-13-01'])(
    'rejects the invalid due date %j',
    (due_date) => {
      expect(validateTodo({ ...valid, due_date })).toEqual({
        due_date: 'Enter a valid date.',
      })
    },
  )
})

describe('isOverdue', () => {
  afterEach(() => vi.useRealTimers())

  const at = (due_date: string | null, completed = false) => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 5, 15, 12, 0, 0))
    return isOverdue({ ...base, due_date, completed })
  }

  it('is true for an open task due in the past', () => {
    expect(at('2026-06-14')).toBe(true)
  })

  it('is false for a completed task due in the past', () => {
    expect(at('2026-06-14', true)).toBe(false)
  })

  it('is false for a task due today', () => {
    expect(at('2026-06-15')).toBe(false)
  })

  it('is false for a task due in the future', () => {
    expect(at('2026-06-16')).toBe(false)
  })

  it('is false without a due date', () => {
    expect(at(null)).toBe(false)
  })
})

describe('formatDate', () => {
  it('formats an ISO date as day, short month and year', () => {
    expect(formatDate('2026-03-05')).toBe('5 Mar 2026')
  })
})
