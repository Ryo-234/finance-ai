'use client'

import { useState, useEffect } from 'react'
import { ArrowLeft, Cpu, Zap } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { api } from '@/core/api'
import { Card } from '@/components/Card'
import { Spinner } from '@/components/Spinner'

export default function SettingsPage() {
  const 路由 = useRouter()
  const [模型列表, 设置模型] = useState<string[]>([])
  const [加载中, 设置加载] = useState(true)

  useEffect(() => {
    api.request<{ models: Array<{ name: string }> }>('/api/models/')
      .then(d => 设置模型(d.models?.map(m => m.name) || []))
      .catch(() => {})
      .finally(() => 设置加载(false))
  }, [])

  return (
    <div className="min-h-screen" style={{ background: '#faf8f5' }}>
      <div className="max-w-3xl mx-auto p-6">
        <div className="flex items-center gap-4 mb-8">
          <button onClick={() => 路由.push('/chat')} className="p-2 rounded-lg cursor-pointer" style={{ color: '#94a3b8' }}>
            <ArrowLeft className="w-5 h-5" />
          </button>
          <h1 className="text-xl font-semibold text-stone-700">设置</h1>
        </div>

        {加载中 ? (
          <div className="flex justify-center py-16"><Spinner className="w-8 h-8" /></div>
        ) : (
          <div className="space-y-6">
            <Card>
              <div className="flex items-center gap-3 mb-4">
                <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: 'rgba(217,119,6,0.1)' }}>
                  <Cpu className="w-5 h-5" style={{ color: '#d97706' }} />
                </div>
                <div>
                  <h3 className="font-medium text-stone-700">模型提供商</h3>
                  <p className="text-xs text-stone-400">MiniMax-M2.7</p>
                </div>
              </div>
            </Card>

            <Card>
              <div className="flex items-center gap-3 mb-4">
                <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: 'rgba(217,119,6,0.1)' }}>
                  <Zap className="w-5 h-5" style={{ color: '#d97706' }} />
                </div>
                <div>
                  <h3 className="font-medium text-stone-700">可用模型</h3>
                  <p className="text-xs text-stone-400">{模型列表.length} 个模型</p>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {模型列表.map(m => (
                  <span key={m} className="px-3 py-1 text-xs rounded-lg" style={{ background: '#f1f5f9', color: '#475569' }}>{m}</span>
                ))}
              </div>
            </Card>
          </div>
        )}
      </div>
    </div>
  )
}
