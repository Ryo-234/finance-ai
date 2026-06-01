'use client'

import { useEffect, useState, useCallback } from 'react'
import { CheckCircle, XCircle, Info, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { toastEvents, type ToastItem } from '@/lib/toast'

const iconMap = {
  success: CheckCircle,
  error: XCircle,
  info: Info,
}

const colorMap = {
  success: { bg: '#f0fdf4', border: '#bbf7d0', text: '#166534', icon: '#22c55e' },
  error:   { bg: '#fef2f2', border: '#fecaca', text: '#991b1b', icon: '#ef4444' },
  info:    { bg: '#eff6ff', border: '#bfdbfe', text: '#1e40af', icon: '#3b82f6' },
}

export function ToastContainer() {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  useEffect(() => {
    const handler = (toast: ToastItem) => {
      setToasts(prev => [...prev, toast])
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t !== toast))
      }, 3000)
    }
    toastEvents.on(handler)
    return () => toastEvents.off(handler)
  }, [])

  const dismiss = useCallback((toast: ToastItem) => {
    setToasts(prev => prev.filter(t => t !== toast))
  }, [])

  if (toasts.length === 0) return null

  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
      {toasts.map((toast, i) => {
        const Icon = iconMap[toast.type]
        const colors = colorMap[toast.type]
        return (
          <div
            key={i}
            className={cn(
              'flex items-start gap-3 px-4 py-3 rounded-xl border shadow-lg animate-message cursor-default'
            )}
            style={{
              background: colors.bg,
              borderColor: colors.border,
            }}
          >
            <Icon className="w-5 h-5 shrink-0 mt-0.5" style={{ color: colors.icon }} />
            <p className="text-sm flex-1" style={{ color: colors.text }}>{toast.message}</p>
            <button onClick={() => dismiss(toast)} className="shrink-0 cursor-pointer">
              <X className="w-4 h-4" style={{ color: colors.text }} />
            </button>
          </div>
        )
      })}
    </div>
  )
}
