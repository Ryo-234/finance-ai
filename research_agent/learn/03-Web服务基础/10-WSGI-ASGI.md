# WSGI / ASGI - "Python Web 框架和服务器之间的接口"

> ⏱ 阅读时间：1 分钟

## 是什么

Python Web 框架（Django/Flask/FastAPI）和 **HTTP 服务器**（Uvicorn/Gunicorn）之间的"翻译官"。

## 类比

饭店的"传菜窗口"：
- 厨师（Django/Flask/FastAPI）做完菜**放窗口**
- 跑堂（Uvicorn）从窗口**端给客人**
- 厨师和跑堂**通过窗口交流**，不用直接对接

## WSGI vs ASGI

| | WSGI | ASGI |
|---|---|---|
| 全称 | Web Server Gateway Interface | Asynchronous Server Gateway Interface |
| 同步/异步 | 同步 | **异步** |
| 用框架 | Django、Flask | **FastAPI**、Django 3.0+ |
| 用服务器 | Gunicorn、uWSGI | **Uvicorn**、Daphne |
| 支持 WebSocket | ❌ | ✅ |

## 你的项目里

```python
# run_api.py 启动方式
import uvicorn
uvicorn.run(app, host="0.0.0.0", port=8001)

# 这里：
# - app = FastAPI 实例（ASGI 应用）
# - uvicorn = ASGI 服务器（接收 HTTP，转给 app）
```

## 流程

```
浏览器请求
  ↓
Uvicorn（HTTP 服务器）
  ↓ ASGI 协议
FastAPI app
  ↓ 调用路由
你的代码
```

## 关键点

- **WSGI 和 ASGI 不兼容**（协议不同）
- 选哪个看框架：FastAPI/Django 3.0+ → ASGI；老 Django/Flask → WSGI
- 你的项目**只用 ASGI**（FastAPI + Uvicorn）

## 怎么配

**一般不用主动配**：
- 框架自带 ASGI/WSGI 应用对象
- 服务器自带协议解析
- 你只要 `uvicorn.run(app)`

## 跟你的项目关系

- 已经在用（`run_api.py` 里 `uvicorn.run(app, ...)`）
- **不用深入研究**协议本身，知道存在即可

## 缺了会怎样

- **不会缺**（FastAPI 自动给你）
- 如果要换服务器（比如 Gunicorn 替代 Uvicorn），了解一下协议有帮助

## 高级：ASGI 生态

- **Uvicorn**：最快，FastAPI 官方推荐
- **Daphne**：Django Channels 用
- **Hypercorn**：支持 HTTP/2
- **Granian**：Rust 写的，最新最猛

## 常见坑

- **混用 WSGI 中间件给 ASGI 用**：报错
- **在 FastAPI 里用同步阻塞代码**（如 `time.sleep`）：会卡死整个 worker
- **没用 lifespan 事件**：启动/关闭时资源没初始化
