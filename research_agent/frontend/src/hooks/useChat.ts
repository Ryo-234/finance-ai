'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { api, Thread, ChatMessage, ChatResponse } from '@/core/api'

interface Task {
  task_type: string
  status: 'pending' | 'running' | 'completed' | 'failed'
}

interface ExtendedThread extends Thread {
  messages: ChatMessage[]
  tasks: Task[]
}

interface CurrentThread {
  threadId: string
  messages: ChatMessage[]
  status: 'idle' | 'busy' | 'streaming'
  tasks: Task[]
}

export interface UseChatReturn {
  threads: Thread[]
  currentThread: CurrentThread | null
  isLoading: boolean
  selectThread: (id: string | undefined) => void
  createThread: () => Promise<void>
  sendMessage: (message: string) => Promise<void>
  deleteThread: (id: string) => Promise<void>
  startPolling: (threadId: string) => void
}

export function useChat(): UseChatReturn {
  const [threads, setThreads] = useState<Thread[]>([])
  const [currentThread, setCurrentThread] = useState<CurrentThread | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const pollingRef = useRef<NodeJS.Timeout | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const currentThreadIdRef = useRef<string | null>(null)

  // 加载线程列表
  const loadThreads = useCallback(async () => {
    try {
      const result = await api.listThreads({ limit: 50 })
      setThreads(result.threads)
    } catch (error) {
      console.error('加载线程列表失败:', error)
    }
  }, [])

  // 初始加载
  useEffect(() => {
    loadThreads()
  }, [loadThreads])

  // 加载线程消息历史
  const loadMessages = useCallback(async (threadId: string) => {
    try {
      const result = await api.getMessages(threadId)
      const messages: ChatMessage[] = result.messages.map((m: any) => ({
        role: m.role as 'human' | 'ai' | 'system',
        content: m.content,
        timestamp: m.timestamp,
      }))
      setCurrentThread(prev => {
        if (!prev || prev.threadId !== threadId) return prev
        return { ...prev, messages }
      })
    } catch (error) {
      console.error('加载消息历史失败:', error)
    }
  }, [])

  // 选择线程
  const selectThread = useCallback((id: string | undefined) => {
    if (!id) {
      currentThreadIdRef.current = null
      setCurrentThread(null)
      return
    }

    // 如果点击的是已选中的线程，不做任何操作，避免刷新丢失历史
    if (currentThreadIdRef.current === id) {
      return
    }

    const thread = threads.find(t => t.thread_id === id)
    if (thread) {
      currentThreadIdRef.current = thread.thread_id
      const extendedThread: CurrentThread = {
        threadId: thread.thread_id,
        messages: [],
        status: thread.status === 'busy' ? 'busy' : 'idle',
        tasks: [],
      }
      setCurrentThread(extendedThread)
    }
  }, [threads])

  // 选中线程后自动加载消息历史
  useEffect(() => {
    if (currentThread?.threadId) {
      loadMessages(currentThread.threadId)
    }
  }, [currentThread?.threadId, loadMessages])

  // 创建新线程
  const createThread = useCallback(async () => {
    setIsLoading(true)
    try {
      const thread = await api.createThread()
      setThreads(prev => [thread, ...prev])
      currentThreadIdRef.current = thread.thread_id
      setCurrentThread({
        threadId: thread.thread_id,
        messages: [],
        status: 'idle',
        tasks: [],
      })
    } catch (error) {
      console.error('创建线程失败:', error)
      throw error
    } finally {
      setIsLoading(false)
    }
  }, [])

  // 发送消息
  const sendMessage = useCallback(async (message: string) => {
    if (!currentThread) return

    // 添加用户消息
    setCurrentThread(prev => {
      if (!prev) return prev
      return {
        ...prev,
        messages: [...prev.messages, { role: 'human', content: message }],
        status: 'streaming',
      }
    })

    try {
      // 使用流式发送
      await api.sendMessageStream(
        {
          message,
          thread_id: currentThread.threadId,
        },
        (text) => {
          // 流式更新消息
          setCurrentThread(prev => {
            if (!prev) return prev
            const lastMessage = prev.messages[prev.messages.length - 1]
            if (lastMessage && lastMessage.role === 'ai') {
              return {
                ...prev,
                messages: [
                  ...prev.messages.slice(0, -1),
                  { ...lastMessage, content: lastMessage.content + text },
                ],
              }
            } else {
              return {
                ...prev,
                messages: [...prev.messages, { role: 'ai', content: text }],
              }
            }
          })
        },
        (response: ChatResponse) => {
          // 完成更新
          setCurrentThread(prev => {
            if (!prev) return prev
            // 更新任务状态
            return {
              ...prev,
              status: 'idle',
              tasks: response.tasks || [],
            }
          })
          // 刷新线程列表
          loadThreads()
        },
        (error: Error) => {
          console.error('发送消息失败:', error)
          setCurrentThread(prev => {
            if (!prev) return prev
            return {
              ...prev,
              status: 'idle',
              messages: [
                ...prev.messages,
                { role: 'ai', content: `错误: ${error.message}` },
              ],
            }
          })
        }
      )
    } catch (error) {
      console.error('发送消息失败:', error)
      setCurrentThread(prev => {
        if (!prev) return prev
        return {
          ...prev,
          status: 'idle',
        }
      })
    }
  }, [currentThread, loadThreads])

  // 删除线程
  const deleteThread = useCallback(async (id: string) => {
    try {
      await api.deleteThread(id)
      setThreads(prev => prev.filter(t => t.thread_id !== id))
      if (currentThread?.threadId === id) {
        currentThreadIdRef.current = null
        setCurrentThread(null)
      }
    } catch (error) {
      console.error('删除线程失败:', error)
      throw error
    }
  }, [currentThread])

  // 轮询线程状态
  const startPolling = useCallback((threadId: string) => {
    // 清除之前的轮询
    if (pollingRef.current) {
      clearInterval(pollingRef.current)
    }

    const poll = async () => {
      try {
        const thread = await api.getThread(threadId)
        setCurrentThread(prev => {
          if (!prev || prev.threadId !== threadId) return prev
          return {
            ...prev,
            status: thread.status === 'busy' ? 'busy' : 'idle',
          }
        })

        // 如果线程不再忙碌，停止轮询
        if (thread.status !== 'busy') {
          if (pollingRef.current) {
            clearInterval(pollingRef.current)
            pollingRef.current = null
          }
        }
      } catch (error) {
        console.error('轮询失败:', error)
      }
    }

    poll()
    pollingRef.current = setInterval(poll, 5000)
  }, [])

  // 组件卸载时清除轮询
  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current)
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [])

  return {
    threads,
    currentThread,
    isLoading,
    selectThread,
    createThread,
    sendMessage,
    deleteThread,
    startPolling,
  }
}
