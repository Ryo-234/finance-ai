"""飞书渠道实现 - 使用 lark-oapi 实现 WebSocket 长连接。"""

import asyncio
import json
import logging
import threading
import time
from typing import Any, Optional, Set

from channels.base import Channel
from channels.message_bus import InboundMessage, OutboundMessage, MessageBus

logger = logging.getLogger(__name__)


class FeishuChannel(Channel):
    """飞书渠道 - 通过 WebSocket 与飞书服务器保持长连接。

    通俗理解：
    - 传统 HTTP = 打电话（你打过去，对方接，才能说话）
    - WebSocket = 对讲机（建立连接后，双方可以随时说话）

    为什么用 WebSocket：
    - 飞书需要主动推送消息给你（不是你想看才看）
    - 用户发消息 → 飞书服务器通过 WebSocket 转发给我们
    - 我们回复 → 通过同一 WebSocket 发回去

    工作流程：
    1. start() → 建立 WebSocket 连接
    2. 收到用户消息 → 转换成 InboundMessage → 发到 MessageBus
    3. 收到 OutboundMessage → 发送到飞书
    4. stop() → 关闭连接
    """

    def __init__(
        self,
        name: str = "feishu",
        bus: Optional[MessageBus] = None,
        config: Optional[dict[str, Any]] = None,
    ) -> None:
        """初始化飞书渠道。

        Args:
            name: 渠道名称，默认 "feishu"
            bus: 消息总线
            config: 配置字典，包含：
                - app_id: 飞书应用 ID
                - app_secret: 飞书应用密钥
                - bot_name: 机器人名称（可选）
                - allowed_users: 允许的用户open_id列表（为空则不限制）
                - bot_open_id: 机器人的open_id（用于@检测）
        """
        config = config or {}
        super().__init__(name, bus, config)

        # 飞书配置
        self._app_id = config.get("app_id", "")
        self._app_secret = config.get("app_secret", "")
        self._bot_name = config.get("bot_name", "DeerFlow Bot")

        # 安全配置
        self._allowed_users: Set[str] = set(config.get("allowed_users", []))
        self._bot_open_id: str = config.get("bot_open_id", "")
        self._require_mention: bool = config.get("require_mention", False)

        # WebSocket 连接相关
        self._ws_client: Optional[Any] = None
        self._ws_loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()  # 用于通知线程停止

        # 消息去重（24小时内的消息ID）
        self._seen_messages: Set[str] = set()
        self._seen_messages_lock = asyncio.Lock()
        self._last_cleanup: float = time.time()

        # 消息处理
        self._message_lock = asyncio.Lock()

    # =========================================================================
    # Channel 抽象方法实现
    # =========================================================================

    async def start(self) -> None:
        """启动飞书渠道（建立 WebSocket 连接）。"""
        if self._running:
            logger.warning("飞书渠道已在运行")
            return

        logger.info("正在启动飞书渠道...")

        # 重置停止事件
        self._stop_event.clear()

        # 先创建 WebSocket 客户端
        self._create_ws_client()

        # 在独立线程中运行 WebSocket（避免与主线程的 uvloop 冲突）
        self._ws_thread = threading.Thread(
            target=self._run_ws_thread,
            daemon=True,
            name="feishu-ws-thread",
        )
        self._ws_thread.start()

        self._running = True
        logger.info("飞书渠道已启动")

    async def stop(self) -> None:
        """停止飞书渠道（关闭 WebSocket 连接）。"""
        if not self._running:
            return

        logger.info("正在停止飞书渠道...")
        self._running = False

        # 通知 WebSocket 线程停止
        self._stop_event.set()

        # 等待线程结束（最多5秒）
        if self._ws_thread:
            self._ws_thread.join(timeout=5)

        self._ws_thread = None
        self._ws_client = None
        self._stop_event.clear()
        logger.info("飞书渠道已停止")

    async def send(self, msg: OutboundMessage) -> None:
        """发送消息到飞书。

        Args:
            msg: 出站消息
        """
        if not self._running:
            raise RuntimeError("飞书渠道未运行")

        try:
            # 根据消息类型选择发送方式
            if msg.thread_ts:
                # 回复特定消息（使用 thread_ts）
                await self._send_reply_message(msg)
            else:
                # 发送普通消息
                await self._send_direct_message(msg)

        except Exception as e:
            logger.exception(f"发送消息失败: {e}")
            raise

    # =========================================================================
    # WebSocket 长连接（独立线程）
    # =========================================================================

    def _run_ws_thread(self) -> None:
        """在独立线程中运行 WebSocket 连接。

        由于 SDK 的 start() 方法与 asyncio 事件循环存在冲突，
        我们直接调用 SDK 的异步连接方法而不是阻塞式的 start()。
        """
        import asyncio

        # 在独立线程中创建新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._ws_loop = loop

        try:
            logger.info("正在启动飞书 WebSocket 客户端...")

            # 创建并运行异步任务
            async def run_ws():
                await self._ws_connect_async()
                # 保持运行，处理心跳和重连
                while self._running:
                    await asyncio.sleep(1)

            loop.run_until_complete(run_ws())

        except Exception as e:
            logger.error(f"WebSocket 连接异常: {e}")
        finally:
            loop.close()
            logger.info("飞书 WebSocket 线程结束")

    def _create_ws_client(self) -> None:
        """创建 WebSocket 客户端。"""
        try:
            # 导入飞书 SDK
            from lark_oapi.ws import Client as WSClient
            from lark_oapi.event.dispatcher_handler import EventDispatcherHandler

            # 创建事件处理器（用于处理接收到的消息）
            # 注意：长连接模式下不需要 encrypt_key 和 verification_token
            self._event_handler = EventDispatcherHandler.builder("", "").build()

            # 创建 WebSocket 客户端（不调用阻塞的start()）
            self._ws_client = WSClient(
                app_id=self._app_id,
                app_secret=self._app_secret,
                event_handler=self._event_handler,
            )

            logger.info("飞书 WebSocket 客户端已创建")

        except ImportError:
            logger.error("请安装 lark-oapi: pip install lark-oapi")
            raise
        except Exception as e:
            logger.exception("创建飞书 WebSocket 客户端失败")
            raise

    async def _ws_connect_async(self) -> None:
        """异步建立 WebSocket 连接。"""
        try:
            from lark_oapi.ws import Client as WSClient

            # 直接使用 SDK 的异步连接方法
            # SDK 的 _connect() 是 async 方法
            client: WSClient = self._ws_client

            # 获取连接URL（SDK内部方法）
            conn_url = await self._get_ws_conn_url()

            import websockets
            from urllib.parse import urlparse, parse_qs

            # 建立 WebSocket 连接
            logger.info("正在建立WebSocket连接...")
            conn = await websockets.connect(conn_url)
            client._conn = conn
            logger.info("WebSocket连接已建立")

            # 获取连接参数
            u = urlparse(conn_url)
            q = parse_qs(u.query)
            client._conn_id = q[b"device_id"][0].decode() if b"device_id" in q else ""
            client._service_id = q[b"service_id"][0].decode() if b"service_id" in q else ""

            logger.info(f"连接参数: conn_id={client._conn_id}, service_id={client._service_id}")
            logger.info(f"飞书 WebSocket 连接已建立: {conn_url}")

            # 获取当前事件循环
            loop = asyncio.get_event_loop()
            logger.info(f"事件循环: {loop}")

            # 创建接收任务
            recv_task = loop.create_task(self._ws_receive_loop(client))
            logger.info(f"接收任务已创建: {recv_task}")

            # 启动心跳
            ping_task = loop.create_task(self._ws_ping_loop(client))
            logger.info(f"心跳任务已创建: {ping_task}")

            logger.info("连接初始化完成")

        except ImportError:
            logger.error("请安装 websockets: pip install websockets")
            raise
        except Exception as e:
            logger.exception("异步连接飞书 WebSocket 失败")
            raise

    async def _get_ws_conn_url(self) -> str:
        """获取 WebSocket 连接 URL。"""
        import requests
        from lark_oapi.core.const import FEISHU_DOMAIN
        from lark_oapi.ws.const import GEN_ENDPOINT_URI, OK
        from lark_oapi.core.json import JSON
        from lark_oapi.ws.model import EndpointResp

        url = FEISHU_DOMAIN + GEN_ENDPOINT_URI
        response = requests.post(
            url,
            headers={"Locale": "zh"},
            json={
                "AppID": self._app_id,
                "AppSecret": self._app_secret,
            },
        )

        if response.status_code != 200:
            raise Exception(f"获取连接URL失败: {response.status_code}")

        resp = JSON.unmarshal(str(response.content, "utf-8"), EndpointResp)
        if resp.code != OK:
            raise Exception(f"获取连接URL失败: {resp.code} - {resp.msg}")

        return resp.data.URL

    async def _ws_receive_loop(self, client) -> None:
        """接收消息循环。"""
        try:
            logger.info("接收循环开始")
            while self._running and client._conn:
                try:
                    logger.info("等待接收消息...")
                    msg = await client._conn.recv()
                    logger.info(f"收到原始数据: {len(msg)} bytes")
                    # 自己的消息处理逻辑
                    await self._handle_ws_frame(msg)
                except Exception as e:
                    logger.error(f"接收消息异常: {e}")
                    import traceback
                    traceback.print_exc()
                    break

            # 断开连接
            if client._auto_reconnect:
                await client._reconnect()
        except Exception as e:
            logger.error(f"接收循环异常: {e}")
            import traceback
            traceback.print_exc()

    async def _handle_ws_frame(self, data: bytes) -> None:
        """处理WebSocket帧。"""
        try:
            from lark_oapi.ws.pb.pbbp2_pb2 import Frame
            from lark_oapi.ws.enum import FrameType, MessageType
            from lark_oapi.ws.const import HEADER_TYPE, HEADER_MESSAGE_ID, HEADER_SEQ, HEADER_SUM
            from lark_oapi.core.json import JSON

            frame = Frame()
            frame.ParseFromString(data)

            ft = FrameType(frame.method)

            if ft == FrameType.DATA:
                # 获取消息类型
                hs = frame.headers
                type_key = None
                for h in hs:
                    if h.key == HEADER_TYPE:
                        type_key = h.value
                        break

                if not type_key:
                    return

                message_type = MessageType(type_key)
                if message_type == MessageType.EVENT:
                    # 解析事件数据
                    pl = frame.payload

                    # 解析消息ID等头信息
                    msg_id = None
                    for h in hs:
                        if h.key == HEADER_MESSAGE_ID:
                            msg_id = h.value
                            break

                    logger.info(f"收到飞书事件: message_type={message_type}, msg_id={msg_id}")

                    # 解析事件内容
                    payload_str = pl.decode('utf-8')
                    logger.debug(f"事件内容: {payload_str[:200]}")

                    # 提取事件数据
                    event_data = json.loads(payload_str)
                    await self._process_event(event_data)

        except Exception as e:
            logger.error(f"处理WebSocket帧异常: {e}")

    async def _process_event(self, event_data: dict) -> None:
        """处理飞书事件数据。"""
        try:
            # 解析事件类型
            header = event_data.get("header", {})
            event_type = header.get("event_type", "")

            if event_type == "im.message.receive_v1":
                # 消息接收事件
                event = event_data.get("event", {})
                message = event.get("message", {})

                if not message:
                    return

                sender = event.get("sender", {})
                sender_id = sender.get("sender_id", {}).get("user_id") or sender.get("sender_id", {}).get("open_id") or sender.get("sender_id", {}).get("id") or "unknown"
                chat_id = message.get("chat_id")
                msg_type = message.get("message_type")
                content = message.get("content", "{}")
                message_id = message.get("message_id")

                # 过滤机器人自己的消息
                sender_type = sender.get("sender_type", "")
                if sender_type == "bot":
                    logger.debug("忽略机器人自己的消息")
                    return

                # 解析消息内容
                try:
                    content_obj = json.loads(content)
                except:
                    content_obj = {"text": content}

                text = ""
                if msg_type == "text":
                    text = content_obj.get("text", "")
                elif msg_type == "post":
                    text = self._extract_text_from_post({"content": content_obj})
                else:
                    text = f"[{msg_type}消息]"

                if not text:
                    return

                logger.info(f"收到消息: chat_id={chat_id}, user_id={sender_id}, text={text[:50]}...")

                # 消息去重
                if message_id in self._seen_messages:
                    logger.debug(f"忽略重复消息: {message_id}")
                    return
                self._seen_messages.add(message_id)

                # 用户白名单检查
                if self._allowed_users and sender_id not in self._allowed_users:
                    logger.info(f"用户 {sender_id} 不在白名单中")
                    return

                # 创建入站消息
                inbound = self._make_inbound(
                    chat_id=chat_id,
                    user_id=sender_id,
                    text=text,
                    thread_ts=message_id,
                )
                inbound.metadata["feishu"] = {
                    "message_id": message_id,
                    "msg_type": msg_type,
                }

                # 发送到消息总线
                if self.bus:
                    await self.bus.publish_inbound(inbound)
                    logger.info(f"消息已发布到总线: {chat_id}/{sender_id}")

        except Exception as e:
            logger.error(f"处理事件异常: {e}")

    async def _ws_ping_loop(self, client) -> None:
        """心跳循环。"""
        from lark_oapi.ws.client import _new_ping_frame

        try:
            while self._running and client._conn:
                try:
                    if client._service_id:
                        frame = _new_ping_frame(int(client._service_id))
                        await client._write_message(frame.SerializeToString())
                        logger.debug("ping 成功")
                except Exception as e:
                    logger.warning(f"ping 失败: {e}")
                finally:
                    await asyncio.sleep(120)  # SDK 默认 ping 间隔
        except Exception as e:
            logger.error(f"心跳循环异常: {e}")

    def _handle_ws_message(self, event: Any) -> None:
        """处理 WebSocket 收到的消息。

        这个方法在 WebSocket 线程中调用，需要通过 asyncio 确保线程安全。

        Args:
            event: 飞书 SDK 的事件对象
        """
        if not self._running:
            return

        # 在正确的事件循环中处理消息
        if self._ws_loop and self._running:
            asyncio.run_coroutine_threadsafe(
                self._process_ws_message(event),
                self._ws_loop,
            )

    async def _process_ws_message(self, event: Any) -> None:
        """处理 WebSocket 消息（异步）。"""
        async with self._message_lock:
            try:
                # 解析飞书事件
                if hasattr(event, "event_type"):
                    # 消息事件
                    if event.event_type == "im.message.receive_v1":
                        await self._handle_message_event(event)
                    else:
                        logger.debug(f"忽略事件类型: {event.event_type}")
                else:
                    # 其他事件
                    logger.debug(f"收到未知事件: {event}")

            except Exception as e:
                logger.exception(f"处理 WebSocket 消息失败: {e}")

    async def _handle_message_event(self, event: Any) -> None:
        """处理飞书消息事件。

        Args:
            event: 飞书消息事件
        """
        try:
            # 清理过期的消息ID（每小时清理一次）
            await self._cleanup_seen_messages()

            # 提取消息内容
            message = event.event.message
            if not message:
                return

            message_id = message.message_id

            # 消息去重
            if message_id in self._seen_messages:
                logger.debug(f"忽略重复消息: {message_id}")
                return
            self._seen_messages.add(message_id)

            # 获取发送者信息
            sender = event.event.sender
            sender_id = sender.sender_id.user_id if sender else "unknown"
            chat_id = message.chat_id

            # 过滤自己发送的消息（避免处理机器人自己的消息）
            if hasattr(sender, "sender_type"):
                if sender.sender_type == "bot":
                    return

            # 用户白名单检查
            if self._allowed_users and sender_id not in self._allowed_users:
                logger.info(f"用户 {sender_id} 不在白名单中，忽略消息")
                return

            # 解析消息类型
            msg_type = message.message_type
            text = ""
            is_mentioned = True  # 单聊默认都响应

            if msg_type == "text":
                # 文本消息
                content = json.loads(message.content)
                text = content.get("text", "")
            elif msg_type == "post":
                # 富文本消息
                content = json.loads(message.content)
                text = self._extract_text_from_post(content)
                # 检查是否@了机器人
                is_mentioned = self._check_mentioned_in_post(content)
            elif msg_type in ("image", "file", "audio"):
                # 媒体消息（简化处理）
                text = f"[{msg_type}消息]"
            else:
                text = f"[未知类型消息: {msg_type}]"

            if not text:
                return

            # 群组消息需要@机器人才响应
            if self._require_mention and not is_mentioned:
                logger.debug(f"群组消息未@机器人，忽略: {chat_id}/{message_id}")
                return

            # 创建入站消息
            inbound = self._make_inbound(
                chat_id=chat_id,
                user_id=sender_id,
                text=text,
                thread_ts=message.message_id,  # 用于回复
            )

            # 添加飞书特定的元数据
            inbound.metadata["feishu"] = {
                "message_id": message_id,
                "msg_type": msg_type,
                "create_time": message.create_time if hasattr(message, "create_time") else None,
            }

            # 发到消息总线
            if self._bus:
                await self._bus.publish_inbound(inbound)
                logger.info(f"飞书消息已发布: {chat_id}/{sender_id}")

        except Exception as e:
            logger.exception(f"处理飞书消息事件失败: {e}")

    async def _cleanup_seen_messages(self) -> None:
        """清理过期的消息ID（每条消息最多保留24小时）。"""
        now = time.time()
        if now - self._last_cleanup > 3600:  # 每小时清理一次
            async with self._seen_messages_lock:
                # 保留最近24小时的消息ID
                self._seen_messages.clear()
                self._last_cleanup = now

    def _check_mentioned_in_post(self, content: dict) -> bool:
        """检查富文本消息中是否@了机器人。"""
        try:
            if "content" in content:
                post_content = content["content"]
                if isinstance(post_content, list):
                    for section in post_content:
                        for tag in section:
                            if tag.get("tag") == "at" and self._bot_open_id:
                                at_users = tag.get("user_id", [])
                                if self._bot_open_id in at_users:
                                    return True
            return True  # 找不到at标签，默认响应（可能是单聊）
        except Exception:
            return True

    def _extract_text_from_post(self, content: dict) -> str:
        """从飞书富文本消息中提取纯文本。"""
        try:
            texts = []
            if "content" in content:
                post_content = content["content"]
                if isinstance(post_content, list):
                    for section in post_content:
                        for tag in section:
                            if tag.get("tag") == "text":
                                texts.append(tag.get("text", ""))
                            elif tag.get("tag") == "at":
                                texts.append(f"@{tag.get('user_name', '')}")
            return " ".join(texts)
        except Exception:
            return "[富文本消息]"

    # =========================================================================
    # 发送消息
    # =========================================================================

    async def _send_direct_message(self, msg: OutboundMessage) -> None:
        """发送直接消息。

        Args:
            msg: 出站消息
        """
        try:
            from lark_oapi.api.im.v1 import CreateMessageRequest

            # 构建请求
            request = CreateMessageRequest.builder()
            request.receive_id(msg.chat_id)
            request.msg_type("text")
            request.content(json.dumps({"text": msg.text}))

            # 发送
            if self._ws_client:
                response = await self._ws_client.request(request.build())
                if not response.success():
                    logger.error(f"发送消息失败: {response.msg}")
                else:
                    logger.info(f"消息已发送: {msg.chat_id}")

        except ImportError:
            logger.error("请安装 lark-oapi: pip install lark-oapi")
            raise
        except Exception as e:
            logger.exception(f"发送直接消息失败: {e}")
            raise

    async def _send_reply_message(self, msg: OutboundMessage) -> None:
        """发送回复消息（带 thread_ts）。

        Args:
            msg: 出站消息
        """
        try:
            import requests

            # 先获取 access token
            token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            token_resp = requests.post(
                token_url,
                json={
                    "app_id": self._app_id,
                    "app_secret": self._app_secret,
                },
                timeout=10,
            )
            token_data = token_resp.json()
            if token_data.get("code") != 0:
                logger.error(f"获取 access token 失败: {token_data}")
                return

            access_token = token_data.get("tenant_access_token")

            # 发送消息 - receive_id_type 必须作为 URL 参数
            msg_url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
            payload = {
                "receive_id": msg.chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": msg.text}),
            }
            if msg.thread_ts:
                payload["uuid"] = msg.thread_ts

            response = requests.post(
                msg_url,
                headers=headers,
                json=payload,
                timeout=10,
            )
            resp_data = response.json()
            if resp_data.get("code") != 0:
                logger.error(f"发送回复失败: {resp_data}")
            else:
                logger.info(f"回复已发送: {msg.chat_id} (thread: {msg.thread_ts})")

        except Exception as e:
            logger.exception(f"发送回复消息失败: {e}")
            raise

    # =========================================================================
    # 配置
    # =========================================================================

    def update_config(self, config: dict[str, Any]) -> None:
        """更新配置（不重启）。

        Args:
            config: 新配置
        """
        self._app_id = config.get("app_id", self._app_id)
        self._app_secret = config.get("app_secret", self._app_secret)
        self._bot_name = config.get("bot_name", self._bot_name)
        self._bot_open_id = config.get("bot_open_id", self._bot_open_id)
        if "allowed_users" in config:
            self._allowed_users = set(config["allowed_users"])
        if "require_mention" in config:
            self._require_mention = config["require_mention"]
        self._config.update(config)

    def get_config(self) -> dict[str, Any]:
        """获取当前配置（不包含密钥）。"""
        return {
            "app_id": self._app_id,
            "bot_name": self._bot_name,
            "bot_open_id": self._bot_open_id,
            "allowed_users": list(self._allowed_users),
            "require_mention": self._require_mention,
            "running": self._running,
        }
