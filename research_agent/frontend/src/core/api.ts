import { env } from '@/env'

const API_BASE = env.apiBaseUrl

export interface Thread {
  thread_id: string
  title: string
  channel: string
  chat_id: string
  created_at: number
  updated_at: number
  status: 'idle' | 'busy'
  message_count: number
}

export interface ChatMessage {
  role: 'human' | 'ai' | 'system'
  content: string
  timestamp?: number
}

export interface Task {
  id: string
  description: string
  task_type: string
  status: 'pending' | 'running' | 'completed' | 'failed'
}

export interface ChatResponse {
  answer: string
  thread_id: string
  sources: Array<{ type: string; url?: string; source?: string }>
  tasks: Task[]
  title?: string
  error?: string
}

export interface SendMessageParams {
  message: string
  thread_id?: string
  channel?: string
  chat_id?: string
  stream?: boolean
}

class APIClient {
  private baseUrl: string

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl
  }

  private async request<T>(path: string, options?: RequestInit): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    })

    if (!res.ok) {
      throw new Error(`API Error: ${res.status} ${res.statusText}`)
    }

    return res.json()
  }

  // 获取线程列表
  async listThreads(params?: { limit?: number; offset?: number; channel?: string }): Promise<{ threads: Thread[]; total: number }> {
    const searchParams = new URLSearchParams()
    if (params?.limit) searchParams.set('limit', String(params.limit))
    if (params?.offset) searchParams.set('offset', String(params.offset))
    if (params?.channel) searchParams.set('channel', params.channel)

    return this.request(`/api/threads/?${searchParams}`)
  }

  // 获取单个线程
  async getThread(threadId: string): Promise<Thread> {
    return this.request(`/api/threads/${threadId}`)
  }

  // 创建新线程
  async createThread(channel = 'api', chatId = 'anonymous'): Promise<Thread> {
    return this.request('/api/threads/', {
      method: 'POST',
      body: JSON.stringify({ channel, chat_id: chatId }),
    })
  }

  // 发送消息（非流式）
  async sendMessage(params: SendMessageParams): Promise<ChatResponse> {
    return this.request('/api/chat/', {
      method: 'POST',
      body: JSON.stringify({
        message: params.message,
        thread_id: params.thread_id,
        channel: params.channel || 'api',
        chat_id: params.chat_id || 'anonymous',
        stream: false,
      }),
    })
  }

  // 流式发送消息
  async sendMessageStream(
    params: SendMessageParams,
    onChunk: (text: string) => void,
    onDone: (response: ChatResponse) => void,
    onError: (error: Error) => void
  ): Promise<void> {
    try {
      const res = await fetch(`${this.baseUrl}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: params.message,
          thread_id: params.thread_id,
          channel: params.channel || 'api',
          chat_id: params.chat_id || 'anonymous',
          stream: true,
        }),
      })

      if (!res.ok) {
        throw new Error(`Stream Error: ${res.status}`)
      }

      const reader = res.body?.getReader()
      if (!reader) throw new Error('No response body')

      const decoder = new TextDecoder()
      let buffer = ''
      let chunkCount = 0

      while (true) {
        const { done, value } = await reader.read()

        if (value) {
          buffer += decoder.decode(value, { stream: true })
        }

        // 按 SSE 标准双换行（\n\n）分割事件
        const events = buffer.split('\n\n')
        // 最后一个可能不完整，保留在 buffer
        buffer = events.pop() || ''

        for (const raw of events) {
          const trimmed = raw.trim()
          if (!trimmed) continue

          // 解析 event: 和 data: 行（可能顺序不同）
          let eventType = ''
          let dataStr = ''
          for (const line of trimmed.split('\n')) {
            if (line.startsWith('event: ')) {
              eventType = line.slice(7).trim()
            } else if (line.startsWith('data: ')) {
              dataStr = line.slice(6)
            }
          }

          if (!eventType || !dataStr) continue

          try {
            const data = JSON.parse(dataStr)
            if (eventType === 'chunk' && data.text) {
              chunkCount++
              onChunk(data.text)
            } else if (eventType === 'done') {
              console.log(`SSE 流式完成: ${chunkCount} 个 chunk, title=${data.title}`)
              onDone(data)
            } else if (eventType === 'error') {
              onError(new Error(data.error))
            }
          } catch {
            // JSON 解析失败，跳过此事件
          }
        }

        if (done) break
      }
    } catch (error) {
      onError(error instanceof Error ? error : new Error('Unknown error'))
    }
  }

  // 删除线程
  async deleteThread(threadId: string): Promise<void> {
    await this.request(`/api/threads/${threadId}`, { method: 'DELETE' })
  }

  // 获取线程消息历史
  async getMessages(threadId: string, limit = 50): Promise<{ thread_id: string; messages: ChatMessage[]; count: number }> {
    return this.request(`/api/chat/${threadId}/messages?limit=${limit}`)
  }

  // 获取记忆
  async getMemory(): Promise<{ memory: string }> {
    return this.request('/api/memory/')
  }
}

export const api = new APIClient(API_BASE)
