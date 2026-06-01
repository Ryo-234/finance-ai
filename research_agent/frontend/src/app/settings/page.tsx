'use client'

import { useState, useEffect } from 'react'
import { ArrowLeft, Cpu, Zap, Server, Shield, ExternalLink } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { api } from '@/core/api'
import { Card } from '@/components/Card'
import { Spinner } from '@/components/Spinner'

// 设置项分组定义
const 设置分组 = [
  {
    标题: '模型配置',
    图标: Cpu,
    项目: [
      { 标签: '提供商', 值: 'MiniMax', 描述: 'MiniMax-M2.7-highspeed' },
      { 标签: '可用模型', 值: 'qwen-plus / qwen-turbo / gpt-4', 描述: '由 /api/models 动态返回' },
    ],
  },
  {
    标题: '连接信息',
    图标: Server,
    项目: [
      { 标签: 'API 地址', 值: 'http://localhost:8001', 描述: '后端服务地址' },
      { 标签: '环境', 值: '开发模式', 描述: '认证中间件处于放行状态' },
    ],
  },
  {
    标题: '安全',
    图标: Shield,
    项目: [
      { 标签: '速率限制', 值: '未启用', 描述: '可配置 API_KEYS 环境变量启用认证' },
    ],
  },
]

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
      {/* 顶部导航 */}
      <div className="sticky top-0 z-20 backdrop-blur-sm" style={{ background: 'rgba(250,248,245,0.9)', borderBottom: '1px solid rgba(226,232,240,0.6)' }}>
        <div className="max-w-4xl mx-auto px-6 h-14 flex items-center gap-4">
          <button onClick={() => 路由.push('/chat')} className="p-1.5 -ml-1.5 rounded-lg transition-colors cursor-pointer" style={{ color: '#64748b' }}>
            <ArrowLeft className="w-5 h-5" />
          </button>
          <h1 className="text-base font-semibold text-stone-700">设置</h1>
        </div>
      </div>

      <div className="max-w-4xl mx-auto p-6 space-y-8">
        {/* 模型标签云 */}
        <section>
          <h2 className="text-sm font-semibold text-stone-400 uppercase tracking-wider mb-4">可用模型</h2>
          <div className="flex flex-wrap gap-2">
            {模型列表.map(m => (
              <span
                key={m}
                className="px-4 py-2 text-sm font-medium rounded-xl transition-colors cursor-default"
                style={{
                  background: m === 'gpt-4' ? 'rgba(34,197,94,0.08)' : 'rgba(217,119,6,0.06)',
                  color: m === 'gpt-4' ? '#16a34a' : '#b45309',
                  border: `1px solid ${m === 'gpt-4' ? 'rgba(34,197,94,0.2)' : 'rgba(217,119,6,0.15)'}`,
                }}
              >
                {m}
                {m === 'qwen-plus' && <span className="text-xs ml-1 opacity-60">默认</span>}
              </span>
            ))}
          </div>
        </section>

        {/* 设置卡片 */}
        {设置分组.map(分组 => (
          <section key={分组.标题}>
            <h2 className="text-sm font-semibold text-stone-400 uppercase tracking-wider mb-4">{分组.标题}</h2>
            <Card>
              <div className="divide-y" style={{ borderColor: 'rgba(226,232,240,0.4)' }}>
                <div className="flex items-center gap-3 pb-4 mb-4">
                  <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
                    style={{ background: 'rgba(217,119,6,0.08)' }}>
                    <分组.图标 className="w-5 h-5" style={{ color: '#d97706' }} />
                  </div>
                  <div>
                    <h3 className="font-medium text-stone-700">{分组.标题}</h3>
                  </div>
                </div>
                {分组.项目.map(项 => (
                  <div key={项.标签} className="flex items-center justify-between py-3 first:pt-0 last:pb-0">
                    <div>
                      <p className="text-sm font-medium text-stone-600">{项.标签}</p>
                      <p className="text-xs text-stone-400 mt-0.5">{项.描述}</p>
                    </div>
                    <span className="text-sm text-stone-500 text-right max-w-[200px] truncate">{项.值}</span>
                  </div>
                ))}
              </div>
            </Card>
          </section>
        ))}

        {/* 页脚链接 */}
        <div className="text-center pt-4 pb-8">
          <a
            href="/docs"
            target="_blank"
            className="inline-flex items-center gap-1.5 text-xs transition-colors cursor-pointer"
            style={{ color: '#94a3b8' }}
          >
            <ExternalLink className="w-3 h-3" />
            API 文档
          </a>
        </div>
      </div>
    </div>
  )
}
