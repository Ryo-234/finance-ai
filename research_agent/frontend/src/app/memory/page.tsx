'use client'

import { useState, useEffect, useCallback } from 'react'
import { ArrowLeft, Trash2, Database } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { api } from '@/core/api'
import { Card } from '@/components/Card'
import { Button } from '@/components/Button'
import { Spinner } from '@/components/Spinner'
import { EmptyState } from '@/components/EmptyState'
import { showToast } from '@/lib/toast'

interface MemoryItem {
  memory: string
}

export default function MemoryPage() {
  const 路由 = useRouter()
  const [记忆列表, 设置记忆] = useState<MemoryItem[]>([])
  const [加载中, 设置加载] = useState(true)

  const 加载记忆 = useCallback(async () => {
    try {
      const 结果 = await api.getMemory()
      设置记忆([{ memory: 结果.memory || '暂无记忆数据' }])
    } catch {
      showToast('error', '加载记忆失败')
    } finally {
      设置加载(false)
    }
  }, [])

  useEffect(() => { 加载记忆() }, [加载记忆])

  const 删除记忆 = async () => {
    // 记忆接口有限，演示用清空
    设置记忆([])
    showToast('success', '记忆已清空')
  }

  if (加载中) {
    return (
      <div className="flex items-center justify-center min-h-screen" style={{ background: '#faf8f5' }}>
        <Spinner className="w-8 h-8" />
      </div>
    )
  }

  return (
    <div className="min-h-screen" style={{ background: '#faf8f5' }}>
      <div className="max-w-3xl mx-auto p-6">
        <div className="flex items-center gap-4 mb-8">
          <button onClick={() => 路由.push('/chat')} className="p-2 rounded-lg cursor-pointer" style={{ color: '#94a3b8' }}>
            <ArrowLeft className="w-5 h-5" />
          </button>
          <h1 className="text-xl font-semibold text-stone-700">记忆管理</h1>
        </div>

        {记忆列表.length === 0 ? (
          <EmptyState
            icon={<Database className="w-12 h-12" />}
            title="暂无记忆"
            description="系统尚未记录任何用户记忆"
          />
        ) : (
          <div className="space-y-4">
            {记忆列表.map((item, i) => (
              <Card key={i} className="flex items-start justify-between">
                <p className="text-sm text-stone-600 whitespace-pre-wrap flex-1">{item.memory}</p>
                <button onClick={删除记忆} className="p-2 rounded-lg cursor-pointer shrink-0 ml-3">
                  <Trash2 className="w-4 h-4" style={{ color: '#ef4444' }} />
                </button>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
