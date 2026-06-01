'use client'

import { useState, useEffect, useCallback } from 'react'
import { ArrowLeft, Trash2, Database, BookOpen, Clock } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { api } from '@/core/api'
import { Card } from '@/components/Card'
import { Button } from '@/components/Button'
import { Spinner } from '@/components/Spinner'
import { EmptyState } from '@/components/EmptyState'
import { showToast } from '@/lib/toast'

// 记忆分区定义
const 分区列表 = [
  { key: 'work_context', 标签: '工作背景', 图标: BookOpen, 描述: '职业角色、技能领域、工作习惯' },
  { key: 'personal_context', 标签: '个人偏好', 图标: BookOpen, 描述: '兴趣、沟通风格、学习方式' },
  { key: 'top_of_mind', 标签: '关注事项', 图标: Clock, 描述: '当前项目、最近活动、优先事务' },
]

export default function 记忆管理页() {
  const 路由 = useRouter()
  const [记忆数据, 设置记忆数据] = useState<any>(null)
  const [加载中, 设置加载中] = useState(true)

  const 加载记忆 = useCallback(async () => {
    try {
      const 结果 = await api.getMemory()
      设置记忆数据(结果)
    } catch {
      showToast('error', '加载记忆失败')
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

  const 用户数据 = 记忆数据?.user || {}
  const 历史数据 = 记忆数据?.history || {}
  const 事实列表 = 记忆数据?.facts || []

  return (
    <div className="min-h-screen" style={{ background: '#faf8f5' }}>
      {/* 顶部导航 */}
      <div className="sticky top-0 z-20 backdrop-blur-sm" style={{ background: 'rgba(250,248,245,0.9)', borderBottom: '1px solid rgba(226,232,240,0.6)' }}>
        <div className="max-w-4xl mx-auto px-6 h-14 flex items-center gap-4">
          <button onClick={() => 路由.push('/chat')} className="p-1.5 -ml-1.5 rounded-lg transition-colors cursor-pointer" style={{ color: '#64748b' }}>
            <ArrowLeft className="w-5 h-5" />
          </button>
          <h1 className="text-base font-semibold text-stone-700">记忆管理</h1>
          <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'rgba(217,119,6,0.1)', color: '#d97706' }}>
            {事实列表.length} 条事实
          </span>
        </div>
      </div>

      <div className="max-w-4xl mx-auto p-6 space-y-8">
        {/* 用户上下文 */}
        <section>
          <h2 className="text-sm font-semibold text-stone-400 uppercase tracking-wider mb-4">用户上下文</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {分区列表.map(分区 => {
              const 数据 = 用户数据[分区.key] || { summary: '', updated_at: '' }
              const 图标 = <分区.图标 className="w-5 h-5" />
              return (
                <Card key={分区.key} className="group transition-shadow duration-200">
                  <div className="flex items-start gap-3">
                    <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0 transition-colors"
                      style={{ background: 'rgba(217,119,6,0.08)' }}>
                      <span style={{ color: '#d97706' }}>{图标}</span>
                    </div>
                    <div className="min-w-0 flex-1">
                      <h3 className="text-sm font-medium text-stone-700 mb-1">{分区.标签}</h3>
                      <p className="text-xs text-stone-400 mb-2">{分区.描述}</p>
                      {数据.summary ? (
                        <p className="text-sm text-stone-600 leading-relaxed">{数据.summary}</p>
                      ) : (
                        <p className="text-xs italic text-stone-300">暂无数据</p>
                      )}
                      {数据.updated_at && (
                        <p className="text-xs text-stone-400 mt-2">{数据.updated_at}</p>
                      )}
                    </div>
                  </div>
                </Card>
              )
            })}
          </div>
        </section>

        {/* 历史上下文 */}
        <section>
          <h2 className="text-sm font-semibold text-stone-400 uppercase tracking-wider mb-4">历史上下文</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {[
              { key: 'recent_months', 标签: '近期', 图标: Clock },
              { key: 'earlier_context', 标签: '早期', 图标: Clock },
              { key: 'long_term_background', 标签: '长期背景', 图标: Clock },
            ].map(item => {
              const 数据 = 历史数据[item.key] || { summary: '', updated_at: '' }
              const 图标 = <item.图标 className="w-4 h-4" />
              return (
                <Card key={item.key} className="group transition-shadow duration-200">
                  <div className="flex items-center gap-2 mb-2">
                    <span style={{ color: '#d97706' }}>{图标}</span>
                    <h3 className="text-sm font-medium text-stone-600">{item.标签}</h3>
                  </div>
                  {数据.summary ? (
                    <p className="text-sm text-stone-500 leading-relaxed">{数据.summary}</p>
                  ) : (
                    <p className="text-xs italic text-stone-300">暂无数据</p>
                  )}
                </Card>
              )
            })}
          </div>
        </section>

        {/* 事实列表 */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-stone-400 uppercase tracking-wider">记忆事实</h2>
          </div>
          {事实列表.length === 0 ? (
            <EmptyState
              icon={<Database className="w-10 h-10" />}
              title="暂无记忆事实"
              description="随着使用，系统会记录你的偏好和习惯"
            />
          ) : (
            <div className="space-y-2">
              {事实列表.map((事实: any, i: number) => (
                <Card key={i} className="flex items-start justify-between group transition-shadow duration-200">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-stone-600">{事实.content}</p>
                    <div className="flex items-center gap-3 mt-2">
                      <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: '#f1f5f9', color: '#64748b' }}>
                        {事实.category}
                      </span>
                      <span className="text-xs text-stone-400">{事实.created_at}</span>
                    </div>
                  </div>
                  <button className="p-1.5 rounded-lg opacity-0 group-hover:opacity-100 transition-all cursor-pointer shrink-0 ml-3">
                    <Trash2 className="w-4 h-4" style={{ color: '#ef4444' }} />
                  </button>
                </Card>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
