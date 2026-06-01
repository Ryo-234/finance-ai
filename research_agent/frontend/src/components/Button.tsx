'use client'

import { type ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { Spinner } from './Spinner'

interface Props {
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
  loading?: boolean
  variant?: 'primary' | 'secondary' | 'ghost'
  className?: string
  type?: 'button' | 'submit'
}

const styles = {
  primary: {
    bg: 'linear-gradient(135deg, #d97706 0%, #f59e0b 100%)',
    text: '#fff',
    shadow: '0 4px 12px rgba(217,119,6,0.25)',
  },
  secondary: {
    bg: 'rgba(248,250,252,0.9)',
    text: '#374151',
    shadow: 'none',
    border: '1px solid rgba(226,232,240,0.8)',
  },
  ghost: {
    bg: 'transparent',
    text: '#64748b',
    shadow: 'none',
  },
}

export function Button({
  children, onClick, disabled, loading,
  variant = 'primary', className, type = 'button',
}: Props) {
  const s = styles[variant]
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || loading}
      className={cn(
        'inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl font-medium text-sm transition-all cursor-pointer disabled:opacity-50',
        className
      )}
      style={{
        background: s.bg,
        color: s.text,
        boxShadow: s.shadow,
        border: 'border' in s ? (s as any).border : 'none',
      }}
    >
      {loading && <Spinner className="w-4 h-4" />}
      {children}
    </button>
  )
}
