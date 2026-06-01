'use client'

import { type ReactNode, useEffect } from 'react'
import { X } from 'lucide-react'

export function Modal({
  open, onClose, title, children,
}: {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
}) {
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => { document.body.style.overflow = '' }
  }, [open])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div
        className="relative z-10 w-full max-w-md rounded-2xl p-6"
        style={{ background: '#fff', boxShadow: '0 20px 60px rgba(0,0,0,0.15)' }}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-stone-700">{title}</h3>
          <button onClick={onClose} className="p-1 rounded-lg cursor-pointer transition-colors" style={{ color: '#94a3b8' }}>
            <X className="w-5 h-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
