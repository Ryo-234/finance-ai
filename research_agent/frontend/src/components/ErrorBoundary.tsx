'use client'

import { Component, type ReactNode } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback

      return (
        <div className="flex items-center justify-center min-h-[200px] p-8">
          <div className="text-center max-w-md">
            <div className="w-14 h-14 mx-auto mb-4 rounded-2xl flex items-center justify-center"
              style={{ background: 'rgba(239,68,68,0.1)' }}>
              <AlertTriangle className="w-7 h-7" style={{ color: '#ef4444' }} />
            </div>
            <h2 className="text-lg font-semibold text-stone-700 mb-2">页面出现了错误</h2>
            <p className="text-sm text-stone-500 mb-6">
              {this.state.error?.message || '未知错误，请刷新重试'}
            </p>
            <button
              onClick={this.handleRetry}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl font-medium text-sm text-white transition-all cursor-pointer"
              style={{
                background: 'linear-gradient(135deg, #d97706 0%, #f59e0b 100%)',
                boxShadow: '0 4px 12px rgba(217,119,6,0.25)',
              }}
            >
              <RefreshCw className="w-4 h-4" />
              重试
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
