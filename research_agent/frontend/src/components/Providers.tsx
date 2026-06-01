'use client'

import { type ReactNode } from 'react'
import { ErrorBoundary } from './ErrorBoundary'
import { ToastContainer } from './Toast'

export function Providers({ children }: { children: ReactNode }) {
  return (
    <ErrorBoundary>
      {children}
      <ToastContainer />
    </ErrorBoundary>
  )
}
