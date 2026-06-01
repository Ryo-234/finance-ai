'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { Search, Plus, Trash2, Send, Bot, User, Loader2, MessageSquare, Sparkles, X, Settings, ArrowLeft, Database } from 'lucide-react'
import Link from 'next/link'
import { useChat } from '@/hooks/useChat'
import { cn } from '@/lib/utils'

// 阶段配置字典 - 按 task_type 动态查找，不再硬编码渲染顺序
const STAGE_CONFIG: Record<string, { label: string; color: string; textColor: string }> = {
  planner:     { label: '规划',   color: '#d97706', textColor: '#92400e' },
  search:      { label: '搜索',   color: '#ea580c', textColor: '#9a3412' },
  knowledge:   { label: '知识库', color: '#78716c', textColor: '#44403c' },
  rag:         { label: 'RAG',    color: '#e11d48', textColor: '#9f1239' },
  synthesizer: { label: '汇总',   color: '#ca8a04', textColor: '#854d0e' },
}

// Logo Animation Component
function AnimatedLogo({ size = 'default' }: { size?: 'small' | 'default' | 'large' }) {
  const sizeClasses = {
    small: 'w-8 h-8',
    default: 'w-10 h-10',
    large: 'w-16 h-16',
  }
  const iconSizes = {
    small: 'w-4 h-4',
    default: 'w-5 h-5',
    large: 'w-8 h-8',
  }

  return (
    <div
      className={cn('rounded-xl flex items-center justify-center', sizeClasses[size])}
      style={{ background: 'linear-gradient(145deg, #d97706 0%, #f59e0b 100%)' }}
    >
      <Sparkles className={cn('text-white', iconSizes[size])} />
    </div>
  )
}

// Empty State Component - 匹配落地页风格
function EmptyState({ onNewThread, isCreating }: { onNewThread: () => void; isCreating: boolean }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center" style={{ background: '#faf8f5' }}>
      {/* Logo */}
      <div className="relative mb-8">
        <div
          className="w-24 h-24 rounded-3xl flex items-center justify-center"
          style={{
            background: 'linear-gradient(145deg, #d97706 0%, #f59e0b 50%, #fbbf24 100%)',
            boxShadow: '0 20px 60px rgba(217, 119, 6, 0.3)',
          }}
        >
          <Sparkles className="w-10 h-10 text-white" />
        </div>
        {/* 装饰光晕 */}
        <div
          className="absolute -inset-4 rounded-full opacity-30"
          style={{
            background: 'radial-gradient(circle, rgba(251,191,36,0.4) 0%, transparent 70%)',
            animation: 'pulse 3s ease-in-out infinite',
          }}
        />
      </div>

      <h2
        className="text-2xl font-bold text-stone-700 mb-2"
        style={{ fontFamily: "'Crimson Pro', serif" }}
      >
        Research Agent
      </h2>
      <p className="text-stone-500 mb-8 text-center max-w-sm">
        智能研究助手，激活你的研究潜能
      </p>

      <button
        onClick={onNewThread}
        disabled={isCreating}
        className={cn(
          'flex items-center gap-2 px-8 py-4 rounded-xl font-semibold text-white',
          'transition-all duration-300 cursor-pointer',
          isCreating ? 'opacity-50' : '',
        )}
        style={{
          background: 'linear-gradient(135deg, #d97706 0%, #f59e0b 100%)',
          boxShadow: '0 8px 24px rgba(217, 119, 6, 0.3)',
        }}
      >
        {isCreating ? (
          <Loader2 className="w-5 h-5 animate-spin" />
        ) : (
          <Plus className="w-5 h-5" />
        )}
        新建会话
      </button>
    </div>
  )
}

export default function HomePage() {
  const {
    threads,
    currentThread,
    isLoading,
    selectThread,
    createThread,
    sendMessage,
    deleteThread,
    startPolling,
  } = useChat()

  const [inputValue, setInputValue] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [isCreating, setIsCreating] = useState(false)
  const [reportType, setReportType] = useState('company_deep')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // 自动滚动到最新消息
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollTop = messagesEndRef.current.scrollHeight
    }
  }, [currentThread?.messages])

  // 选择线程时开始轮询
  useEffect(() => {
    if (currentThread?.threadId) {
      startPolling(currentThread.threadId)
    }
  }, [currentThread?.threadId, startPolling])

  // Auto-resize textarea
  const adjustTextareaHeight = useCallback(() => {
    const textarea = inputRef.current
    if (textarea) {
      textarea.style.height = 'auto'
      textarea.style.height = Math.min(textarea.scrollHeight, 128) + 'px'
    }
  }, [])

  useEffect(() => {
    adjustTextareaHeight()
  }, [inputValue, adjustTextareaHeight])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!inputValue.trim() || currentThread?.status === 'streaming') return

    const message = inputValue
    setInputValue('')

    try {
      await sendMessage(message, reportType)
    } catch (error) {
      console.error('Send failed:', error)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  const handleNewThread = async () => {
    setIsCreating(true)
    try {
      await createThread()
      inputRef.current?.focus()
    } catch (error) {
      console.error('Create thread failed:', error)
    } finally {
      setIsCreating(false)
    }
  }

  // 过滤线程（支持按标题或 ID 搜索）
  const filteredThreads = threads.filter(t =>
    t.thread_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (t.title && t.title.toLowerCase().includes(searchQuery.toLowerCase()))
  )

  // 获取需要显示的非 pending 阶段（渐进式披露：只显示已启动/已完成/失败的）
  const getActiveStages = () => {
    if (!currentThread?.tasks.length) return []
    return currentThread.tasks.filter(t => t.status !== 'pending')
  }

  const activeStages = getActiveStages()

  return (
    <div className="flex h-screen" style={{ background: '#faf8f5' }}>
      {/* 侧边栏 */}
      <aside
        className="w-72 flex flex-col border-r"
        style={{ background: 'rgba(255,255,255,0.8)', borderColor: 'rgba(226,232,240,0.8)' }}
      >
        {/* Logo 区域 */}
        <div className="p-5 border-b" style={{ borderColor: 'rgba(226,232,240,0.8)' }}>
          <div className="flex items-center gap-3">
            <AnimatedLogo size="default" />
            <div>
              <h1
                className="font-semibold text-stone-700"
                style={{ fontFamily: "'Crimson Pro', serif" }}
              >
                Research Agent
              </h1>
              <p className="text-xs text-stone-400">智能研究助手</p>
            </div>
          </div>
        </div>

        {/* 新建按钮 */}
        <div className="p-4">
          <button
            onClick={handleNewThread}
            disabled={isLoading || isCreating}
            className={cn(
              'w-full flex items-center justify-center gap-2 px-4 py-2.5 text-white rounded-xl font-medium text-sm',
              'transition-all duration-200 cursor-pointer',
              'disabled:opacity-50',
            )}
            style={{
              background: 'linear-gradient(135deg, #d97706 0%, #f59e0b 100%)',
              boxShadow: '0 4px 12px rgba(217, 119, 6, 0.25)',
            }}
          >
            {isCreating ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Plus className="w-4 h-4" />
            )}
            新建会话
          </button>
        </div>

        {/* 搜索 */}
        <div className="px-4 pb-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-400" />
            <input
              type="text"
              placeholder="搜索会话..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-2 rounded-lg text-sm transition-all cursor-text"
              style={{
                background: 'rgba(248,250,252,0.8)',
                border: '1px solid rgba(226,232,240,0.8)',
                color: '#374151',
              }}
            />
          </div>
        </div>

        {/* 会话列表 */}
        <div className="flex-1 overflow-y-auto px-3 pb-4">
          <div className="text-xs font-medium text-stone-400 uppercase tracking-wider px-2 mb-2">
            会话列表
          </div>
          {filteredThreads.length === 0 ? (
            <div className="py-8 text-center text-stone-400 text-sm">
              {searchQuery ? '无匹配会话' : '暂无会话记录'}
            </div>
          ) : (
            <div className="space-y-1">
              {filteredThreads.map((thread) => (
                <div
                  key={thread.thread_id}
                  onClick={() => selectThread(thread.thread_id)}
                  className={cn(
                    'group flex items-center gap-3 px-3 py-3 rounded-xl cursor-pointer transition-all duration-200',
                  )}
                  style={{
                    background: currentThread?.threadId === thread.thread_id
                      ? 'rgba(217,119,6,0.1)'
                      : 'transparent',
                    border: currentThread?.threadId === thread.thread_id
                      ? '1px solid rgba(217,119,6,0.2)'
                      : '1px solid transparent',
                  }}
                >
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 transition-colors"
                    style={{
                      background: currentThread?.threadId === thread.thread_id
                        ? '#d97706'
                        : 'rgba(248,250,252,0.8)',
                    }}
                  >
                    <MessageSquare
                      className="w-4 h-4"
                      style={{
                        color: currentThread?.threadId === thread.thread_id ? '#fff' : '#94a3b8',
                      }}
                    />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-stone-700 truncate">
                        {thread.title || thread.thread_id}
                      </span>
                      {thread.status === 'busy' && (
                        <span
                          className="w-2 h-2 rounded-full animate-pulse"
                          style={{ background: '#22c55e' }}
                        />
                      )}
                    </div>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      deleteThread(thread.thread_id)
                    }}
                    className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg transition-all cursor-pointer"
                  >
                    <Trash2 className="w-4 h-4" style={{ color: '#ef4444' }} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 底部状态 */}
        <div className="p-4 border-t" style={{ borderColor: 'rgba(226,232,240,0.8)' }}>
          <div className="flex items-center gap-2 text-xs text-stone-400">
            <span className="w-2 h-2 rounded-full" style={{ background: '#22c55e' }} />
            <span>系统正常</span>
          </div>
        </div>
      </aside>

      {/* 主区域 */}
      <main className="flex-1 flex flex-col relative">
        {currentThread ? (
          <>
            {/* 顶部状态栏 */}
            <div
              className="h-16 flex items-center px-6 justify-between border-b"
              style={{ background: 'rgba(255,255,255,0.8)', borderColor: 'rgba(226,232,240,0.8)' }}
            >
              {/* 左侧信息 */}
              <div className="flex items-center gap-3">
                <div
                  className="w-8 h-8 rounded-lg flex items-center justify-center"
                  style={{ background: 'rgba(217,119,6,0.1)' }}
                >
                  <MessageSquare className="w-4 h-4" style={{ color: '#d97706' }} />
                </div>
                <div>
                  <div className="font-medium text-sm text-stone-700 truncate max-w-xs">
                    {currentThread.title || `会话 ${currentThread.threadId}`}
                  </div>
                </div>
              </div>

              {/* 动态阶段时间线 —— 渐进式披露，只显示实际执行的阶段 */}
              <div className="flex items-center gap-3">
                {activeStages.length > 0 && (
                  <div className="flex items-center">
                    {activeStages.map((task, index) => {
                      const cfg = STAGE_CONFIG[task.task_type] || STAGE_CONFIG.planner
                      const isRunning = task.status === 'running'
                      const isCompleted = task.status === 'completed'
                      const isFailed = task.status === 'failed'
                      const isLast = index === activeStages.length - 1

                      return (
                        <div key={`${task.task_type}-${index}`} className="flex items-center">
                          {/* 阶段节点 */}
                          <div
                            className="flex flex-col items-center animate-stageEnter"
                            style={{ animationDelay: `${index * 0.25}s` }}
                          >
                            <div className="relative flex items-center justify-center">
                              {/* 活跃脉冲外环 */}
                              {isRunning && (
                                <div
                                  className="absolute rounded-full animate-stagePulse"
                                  style={{
                                    width: 32, height: 32,
                                    border: `2px solid ${cfg.color}`,
                                  }}
                                />
                              )}
                              {/* 节点圆点 */}
                              <div
                                className="w-7 h-7 rounded-full flex items-center justify-center transition-all duration-500 relative z-10"
                                style={{
                                  background: isFailed
                                    ? '#fef2f2'
                                    : isCompleted
                                    ? cfg.color
                                    : cfg.color + '18',
                                  border: isRunning ? `2px solid ${cfg.color}` : '2px solid transparent',
                                }}
                              >
                                {isFailed ? (
                                  <span className="text-xs font-bold" style={{ color: '#ef4444' }}>!</span>
                                ) : isCompleted ? (
                                  <span className="animate-checkPop text-white text-xs font-bold">✓</span>
                                ) : isRunning ? (
                                  <Loader2 className="w-3.5 h-3.5 animate-spin" style={{ color: cfg.color }} />
                                ) : null}
                              </div>
                            </div>
                            {/* 阶段标签 */}
                            <span
                              className="text-[10px] mt-1 font-medium whitespace-nowrap"
                              style={{
                                color: isFailed ? '#ef4444' : isCompleted ? '#64748b' : cfg.textColor,
                                fontFamily: isRunning ? "'IBM Plex Sans', monospace" : undefined,
                              }}
                            >
                              {cfg.label}
                            </span>
                          </div>
                          {/* 连接线 —— 非最后一项时显示 */}
                          {!isLast && (
                            <div className="relative mx-1 mb-4" style={{ width: 28, height: 2 }}>
                              <div
                                className="absolute inset-0 rounded-full"
                                style={{ background: 'rgba(226,232,240,0.6)' }}
                              />
                              <div
                                className="absolute inset-0 rounded-full animate-lineGrow"
                                style={{
                                  background: isCompleted ? cfg.color : 'transparent',
                                }}
                              />
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}

              </div>

              {/* 右侧操作 */}
              <div className="flex items-center gap-1">
                <Link href="/memory" className="p-2 rounded-lg transition-colors cursor-pointer" style={{ color: '#94a3b8' }} title="记忆管理">
                  <Database className="w-4 h-4" />
                </Link>
                <Link href="/settings" className="p-2 rounded-lg transition-colors cursor-pointer" style={{ color: '#94a3b8' }} title="设置">
                  <Settings className="w-4 h-4" />
                </Link>
                <button
                  onClick={() => selectThread(undefined)}
                  className="p-2 rounded-lg transition-colors cursor-pointer"
                  style={{ color: '#94a3b8' }}
                  title="返回"
                >
                  <ArrowLeft className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* 消息区域 */}
            <div
              ref={messagesEndRef}
              className="flex-1 overflow-y-auto p-6"
              style={{ scrollBehavior: 'smooth' }}
            >
              {currentThread.messages.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center">
                  <div
                    className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
                    style={{ background: 'rgba(217,119,6,0.1)' }}
                  >
                    <Bot className="w-8 h-8" style={{ color: '#d97706' }} />
                  </div>
                  <h2 className="text-lg font-medium text-stone-700 mb-1">开始研究之旅</h2>
                  <p className="text-sm text-stone-400 text-center">
                    输入你的研究问题，AI 将自动规划、搜索、整合答案
                  </p>
                </div>
              ) : (
                <div className="space-y-6 max-w-3xl mx-auto">
                  {currentThread.messages.map((message, index) => (
                    <div
                      key={index}
                      className={cn('flex gap-4 animate-message', message.role === 'human' ? 'justify-end' : 'justify-start')}
                    >
                      {message.role === 'ai' && (
                        <div
                          className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
                          style={{
                            background: 'linear-gradient(135deg, #d97706 0%, #f59e0b 100%)',
                            boxShadow: '0 4px 12px rgba(217, 119, 6, 0.25)',
                          }}
                        >
                          <Bot className="w-5 h-5 text-white" />
                        </div>
                      )}
                      <div
                        className="max-w-[75%] rounded-2xl px-4 py-3 transition-all duration-200"
                        style={{
                          background: message.role === 'human'
                            ? 'linear-gradient(135deg, #d97706 0%, #f59e0b 100%)'
                            : '#fff',
                          color: message.role === 'human' ? '#fff' : '#374151',
                          boxShadow: message.role === 'human'
                            ? '0 4px 12px rgba(217, 119, 6, 0.25)'
                            : '0 1px 3px rgba(0,0,0,0.05)',
                          borderRadius: message.role === 'human' ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
                        }}
                      >
                        <p className="whitespace-pre-wrap break-all leading-relaxed">
                          {message.content}
                          {currentThread.status === 'streaming' && index === currentThread.messages.length - 1 && message.role === 'ai' && (
                            <span
                              className="inline-block w-2 h-4 ml-1 animate-pulse"
                              style={{ background: '#d97706' }}
                            />
                          )}
                        </p>
                      </div>
                      {message.role === 'human' && (
                        <div
                          className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
                          style={{ background: 'rgba(226,232,240,0.8)' }}
                        >
                          <User className="w-5 h-5" style={{ color: '#64748b' }} />
                        </div>
                      )}
                    </div>
                  ))}

                  {/* Streaming indicator */}
                  {currentThread.status === 'streaming' && currentThread.messages[currentThread.messages.length - 1]?.role === 'human' && (
                    <div className="flex gap-4">
                      <div
                        className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
                        style={{
                          background: 'linear-gradient(135deg, #d97706 0%, #f59e0b 100%)',
                          boxShadow: '0 4px 12px rgba(217, 119, 6, 0.25)',
                        }}
                      >
                        <Bot className="w-5 h-5 text-white" />
                      </div>
                      <div
                        className="rounded-2xl rounded-tl-sm px-4 py-3"
                        style={{
                          background: '#fff',
                          boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
                        }}
                      >
                        <div className="flex items-center gap-2 text-stone-400">
                          <Loader2 className="w-4 h-4 animate-spin" />
                          <span className="text-sm">正在思考...</span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* 输入框 */}
            <div
              className="border-t p-4"
              style={{ background: 'rgba(255,255,255,0.8)', borderColor: 'rgba(226,232,240,0.8)' }}
            >
              <form onSubmit={handleSubmit} className="max-w-3xl mx-auto">
                {/* 报告类型选择器 */}
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs text-stone-400 flex-shrink-0">报告类型：</span>
                  <div className="flex gap-1 flex-wrap">
                    {[
                      { value: 'company_deep', label: '公司深度' },
                      { value: 'industry_research', label: '行业研究' },
                      { value: 'macro_brief', label: '宏观简报' },
                      { value: 'strategy_daily', label: '策略日报' },
                    ].map((item) => (
                      <button
                        key={item.value}
                        type="button"
                        onClick={() => setReportType(item.value)}
                        className="px-2.5 py-1 rounded-full text-xs font-medium transition-all cursor-pointer"
                        style={{
                          background: reportType === item.value ? '#fef3c7' : '#f8fafc',
                          color: reportType === item.value ? '#92400e' : '#78716c',
                          border: reportType === item.value ? '1px solid #f59e0b' : '1px solid #e2e8f0',
                        }}
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div
                  className="relative flex items-end gap-3 rounded-xl p-1 transition-colors"
                  style={{
                    background: '#fff',
                    border: '2px solid rgba(226,232,240,0.8)',
                  }}
                >
                  <textarea
                    ref={inputRef}
                    value={inputValue}
                    onChange={(e) => {
                      setInputValue(e.target.value)
                      adjustTextareaHeight()
                    }}
                    onKeyDown={handleKeyDown}
                    placeholder="输入你的研究问题..."
                    disabled={currentThread.status === 'streaming'}
                    className="flex-1 px-3 py-2.5 resize-none focus:outline-none text-sm min-h-[44px] cursor-text"
                    style={{ color: '#374151' }}
                    rows={1}
                  />
                  <button
                    type="submit"
                    disabled={!inputValue.trim() || currentThread.status === 'streaming'}
                    className={cn(
                      'px-5 py-2.5 rounded-lg font-medium text-sm flex items-center gap-2 transition-all flex-shrink-0 cursor-pointer',
                    )}
                    style={{
                      background:
                        inputValue.trim() && currentThread.status !== 'streaming'
                          ? 'linear-gradient(135deg, #d97706 0%, #f59e0b 100%)'
                          : 'rgba(248,250,252,0.8)',
                      color:
                        inputValue.trim() && currentThread.status !== 'streaming' ? '#fff' : '#94a3b8',
                      boxShadow:
                        inputValue.trim() && currentThread.status !== 'streaming'
                          ? '0 4px 12px rgba(217, 119, 6, 0.25)'
                          : 'none',
                    }}
                  >
                    {currentThread.status === 'streaming' ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        生成中
                      </>
                    ) : (
                      <>
                        <Send className="w-4 h-4" />
                        发送
                      </>
                    )}
                  </button>
                </div>
                <div className="flex items-center justify-between mt-2 px-1">
                  <span className="text-xs text-stone-400">Enter 发送，Shift + Enter 换行</span>
                  <span className="text-xs text-stone-400">
                    {inputValue.length > 0 && `${inputValue.length} 字符`}
                  </span>
                </div>
              </form>
            </div>
          </>
        ) : (
          <EmptyState onNewThread={handleNewThread} isCreating={isCreating} />
        )}
      </main>
    </div>
  )
}
