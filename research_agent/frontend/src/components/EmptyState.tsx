import { type ReactNode } from 'react'

export function EmptyState({
  icon, title, description, action,
}: {
  icon: ReactNode
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="mb-4" style={{ color: '#94a3b8' }}>{icon}</div>
      <h3 className="text-base font-medium text-stone-600 mb-1">{title}</h3>
      {description && <p className="text-sm text-stone-400 max-w-sm">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}
