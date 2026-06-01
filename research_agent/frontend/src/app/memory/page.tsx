'use client'

import { useState, useEffect, useCallback } from 'react'
import { ArrowLeft, Database } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { api } from '@/core/api'
import { Card } from '@/components/Card'
import { Spinner } from '@/components/Spinner'
import { EmptyState } from '@/components/EmptyState'

export default function 记忆管理页() {
  const 路由 = useRouter()
  const [事实列表, 设置事实] = useState<any[]>([])
  const [加载中, 设置加载中] = useState(true)

  const 加载记忆 = useCallback(async () => {
    try {
      const 结果 = await api.getMemory()
      设置事实((结果 as any).facts || [])
    } catch {
      设置事实([])
    } finally {
      设置加载中(false)
    }
  }, [])

  useEffect(() => { 加载记忆() }, [加载记忆])

  if (加载中) {
    return (
      <div className="flex items-center justify-center min-h-screen" style={{ background: '#faf8f5' }}>
        <Spinner className="w-8 h-8" style={{ color: '#d97706' }} />
      </div>
    )
  }

  return (
    <div className="min-h-screen flex flex-col" style={{ background: '#faf8f5' }}>
      <div className="sticky top-0 z-20 backdrop-blur-sm" style={{ background: 'rgba(250,248,245,0.9)', borderBottom: '1px solid rgba(226,232,240,0.6)' }}>
        <div className="max-w-3xl mx-auto px-6 h-14 flex items-center gap-4">
          <button onClick={() => 路由.push('/chat')} className="p-1.5 -ml-1.5 rounded-lg transition-colors cursor-pointer" style={{ color: '#64748b' }}>
            <ArrowLeft className="w-5 h-5" />
          </button>
          <h1 className="text-base font-semibold text-stone-700">记忆管理</h1>
          {事实列表.length > 0 && (
            <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'rgba(217,119,6,0.1)', color: '#d97706' }}>
              {事实列表.length} 条
            </span>
          )}
        </div>
      </div>

      <div className="max-w-3xl mx-auto p-6 flex-1 flex items-center justify-center">
        {事实列表.length === 0 ? (
          <EmptyState
            icon={<Database className="w-10 h-10" />}
            title="暂无记忆"
            description="系统尚未记录用户记忆，随使用逐渐积累"
          />
        ) : (
          <div className="space-y-3">
            {事实列表.map((事实: any, i: number) => (
              <Card key={i} className="transition-shadow duration-200">
                <p className="text-sm text-stone-600 leading-relaxed">{事实.content}</p>
                <div className="flex items-center gap-3 mt-2">
                  {事实.category && (
                    <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: '#f1f5f9', color: '#64748b' }}>
                      {事实.category}
                    </span>
                  )}
                  {事实.created_at && (
                    <span className="text-xs text-stone-400">{事实.created_at}</span>
                  )}
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
