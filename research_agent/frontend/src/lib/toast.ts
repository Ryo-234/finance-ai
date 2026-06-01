type ToastType = 'success' | 'error' | 'info'

export interface ToastItem {
  type: ToastType
  message: string
}

type Handler = (toast: ToastItem) => void

// 简单的发布/订阅事件总线
class ToastEmitter {
  private handlers: Set<Handler> = new Set()

  on(handler: Handler) { this.handlers.add(handler) }
  off(handler: Handler) { this.handlers.delete(handler) }
  emit(toast: ToastItem) { this.handlers.forEach(h => h(toast)) }
}

export const toastEvents = new ToastEmitter()

export function showToast(type: ToastType, message: string) {
  toastEvents.emit({ type, message })
}
