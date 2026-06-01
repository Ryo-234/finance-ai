'use client'

import { useState, useEffect } from 'react'
import { ArrowLeft, Cpu, Server } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { api } from '@/core/api'
import { Card } from '@/components/Card'
import { Spinner } from '@/components/Spinner'

export default function 设置页() {
  const 路由 = useRouter()
  const [模型列表, 设置模型] = useState<string[]>([])
  const [加载中, 设置加载中] = useState(true)

  useEffect(() => {
    api.request<{ models: Array<{ name: string }> }>('/api/models/')
      .then(d => 设置模型(d.models?.map((m: any) => m.name) || []))
      .catch(() => {})
      .finally(() => 设置加载中(false))
  }, [])

  if (加载中) {
    return (
      <div className="flex items-center justify-center min-h-screen" style={{ background: '#faf8f5' }}>
        <Spinner className="w-8 h-8" style={{ color: '#d97706' }} />
      </div>
    )
  }

  return (
    <div className="min-h-screen" style={{ background: '#faf8f5' }}>
      <div className="sticky top-0 z-20 backdrop-blur-sm" style={{ background: 'rgba(250,248,245,0.9)', borderBottom: '1px solid rgba(226,232,240,0.6)' }}>
        <div className="max-w-3xl mx-auto px-6 h-14 flex items-center gap-4">
          <button onClick={() => 路由.push('/chat')} className="p-1.5 -ml-1.5 rounded-lg transition-colors cursor-pointer" style={{ color: '#64748b' }}>
            <ArrowLeft className="w-5 h-5" />
          </button>
          <h1 className="text-base font-semibold text-stone-700">设置</h1>
        </div>
      </div>

      <div className="max-w-3xl mx-auto p-6 space-y-6">
        {/* 模型 */}
        <Card>
          <div className="flex items-center gap-3 mb-4">
            <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: 'rgba(217,119,6,0.08)' }}>
              <Cpu className="w-5 h-5" style={{ color: '#d97706' }} />
            </div>
            <div>
              <h3 className="font-medium text-stone-700">模型配置</h3>
              <p className="text-xs text-stone-400">MiniMax-M2.7-highspeed</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {模型列表.map(m => (
              <span key={m} className="px-3 py-1.5 text-sm rounded-lg" style={{ background: '#f1f5f9', color: '#475569' }}>
                {m}
              </span>
            ))}
          </div>
        </Card>

        {/* 服务信息 */}
        <Card>
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: 'rgba(217,119,6,0.08)' }}>
              <Server className="w-5 h-5" style={{ color: '#d97706' }} />
            </div>
            <div>
              <h3 className="font-medium text-stone-700">服务状态</h3>
              <p className="text-xs text-stone-400">后端 http://localhost:8001 · 开发模式</p>
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
}
