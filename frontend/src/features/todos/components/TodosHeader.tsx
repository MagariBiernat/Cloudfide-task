import { Plus } from 'lucide-react'
import { Button, Heading, Text } from '../../../design-system'

export function TodosHeader({
  disabled,
  completedCount = 0,
  onCreate,
  onClearCompleted,
}: {
  disabled: boolean
  completedCount?: number
  onCreate: () => void
  onClearCompleted?: () => void
}) {
  return (
    <section className="row spread" aria-labelledby="page-title">
      <div className="stack compact">
        <Heading id="page-title">Tasks</Heading>
        <Text muted>Create, organize, and complete tasks.</Text>
      </div>
      <div className="row">
        {completedCount > 0 && onClearCompleted && (
          <Button
            variant="secondary"
            disabled={disabled}
            onClick={onClearCompleted}
          >
            Clear completed ({completedCount})
          </Button>
        )}
        <Button disabled={disabled} onClick={onCreate}>
          <Plus size={18} aria-hidden="true" />
          New task
        </Button>
      </div>
    </section>
  )
}
