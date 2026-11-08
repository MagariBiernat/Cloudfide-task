---
name: frontend-test-conventions
description: Conventions, helpers and proven patterns for writing Vitest + React Testing Library unit tests for the Taskly React/TypeScript frontend (components, React Query hooks, API client, utils). Use whenever you create or update frontend/src/**/*.test.ts(x).
---

# Frontend unit-test conventions (Vitest + RTL)

Distilled from the existing suite. Match it. Examples: [reference/examples.md](reference/examples.md).

## Layout and style

- Co-located: `X.tsx` → `X.test.tsx`, `x.ts` → `x.test.ts`.
- Top-level `it('describes the behaviour…')`, no `describe` nesting.
- Import explicitly: `import { beforeEach, expect, it, vi } from 'vitest'`.
- `beforeEach(() => vi.clearAllMocks())` when module mocks are shared between tests.
- Query by role / label / text (`getByRole('button', { name: 'Try again' })`); `getByTestId`
  only where the design-system mock exposes one (e.g. `alert`).
- `const user = userEvent.setup()` for interactions; `await` every interaction.
- Async: `findBy*` / `waitFor`; time: `vi.useFakeTimers()` + `vi.setSystemTime(...)` and
  `vi.useRealTimers()` afterwards. Never `setTimeout` waits.
- No snapshots, no `.only`/`.skip`, no real network. Prettier style: single quotes, no semicolons.

## Helpers

| helper | use |
|---|---|
| `src/test/setup.ts` | jest-dom matchers + RTL cleanup (global, **do not edit**) |
| `src/test/todoFixture.ts` | `todoFixture: Todo` — spread for variants `{ ...todoFixture, completed: true }` |
| `src/design-system/mocks.tsx` | lightweight DS mocks: `vi.mock('<rel>/design-system', () => import('<rel>/design-system/mocks'))` |

New shared helpers may be added under `src/test/` (e.g. `renderWithClient.tsx`).

## Patterns by kind

- **Components** — mock the design system as above; mock child components and hooks with
  `vi.mock('./hooks/useX', () => ({ useX: vi.fn() }))`, then
  `vi.mocked(useX).mockReturnValue({...} as unknown as ReturnType<typeof useX>)`.
  Assert rendered output and callback calls; ordering via `mock.invocationCallOrder`.
- **React Query hooks** — real `QueryClient`, mocked API module:
  ```ts
  vi.mock('../api/todos', () => ({ todosApi: { create: vi.fn() } }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  const { result } = renderHook(() => useCreateTodoMutation(), { wrapper })
  ```
  Seed with `client.setQueryData(todoKeys.list, [...])`, act with
  `await act(() => result.current.mutateAsync(input))`, assert `client.getQueryData(todoKeys.list)`.
  A **fresh client per test**. Test files that render JSX must be `.test.tsx`.
- **API client (`api/todos.ts`)** — `vi.mock('../../../lib/http', () => ({ request: vi.fn() }))`;
  assert path, method and serialised body.
- **`lib/http.ts`** — `vi.stubGlobal('fetch', vi.fn())`, return `new Response(JSON.stringify(body), { status })`
  or reject; restore with `vi.unstubAllGlobals()` in `afterEach`. Cover: `/api` prefix + headers,
  network error message, aborted signal rethrows, 422 message, string `detail`, non-JSON error
  body, 204 → `undefined`, 200 → JSON.
- **Pure utils** — table-driven `it.each` is fine; use fake timers for date logic (`isOverdue`).

## Running

```bash
python3 .claude/skills/test-runner/scripts/run_tests.py frontend --root . frontend/src/<file>.test.ts --shuffle
```
