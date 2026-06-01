import type { CSSProperties } from 'react'
import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

export function Spinner({ className, style }: { className?: string; style?: CSSProperties }) {
  return <Loader2 className={cn('animate-spin', className)} style={style} />
}
