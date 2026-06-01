import { type ReactNode } from 'react'
import { cn } from '@/lib/utils'

export function Card({
  children, className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn('rounded-xl p-5', className)}
      style={{
        background: '#fff',
        border: '1px solid rgba(226,232,240,0.8)',
        boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
      }}
    >
      {children}
    </div>
  )
}
