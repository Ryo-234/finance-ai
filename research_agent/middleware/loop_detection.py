"""循环检测中间件 - 检测并阻止重复的 Agent 调用循环。

参考 DeerFlow 的 LoopDetectionMiddleware 设计，提供：
1. Hash 检测：检测完全相同的调用序列
2. 频率检测：检测同一工具被调用多次（跨文件读取循环）
3. 智能 Key：对 read_file 等操作按路径桶分组，避免误报

该中间件是 P0 级别安全机制，防止 Agent 在相同操作上无限循环。
"""

import hashlib
import json
import logging
import threading
from collections import OrderedDict, defaultdict
from copy import deepcopy
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from middleware.base import BaseMiddleware, MiddlewareResult

logger = logging.getLogger(__name__)

# 默认配置
_DEFAULT_WARN_THRESHOLD = 3  # 注入警告前的重复次数
_DEFAULT_HARD_LIMIT = 5  # 强制停止前的重复次数
_DEFAULT_WINDOW_SIZE = 20  # 滑动窗口大小
_DEFAULT_MAX_TRACKED_THREADS = 100  # 最大跟踪线程数
_DEFAULT_TOOL_FREQ_WARN = 30  # 同类型工具调用频率警告阈值
_DEFAULT_TOOL_FREQ_HARD_LIMIT = 50  # 同类型工具调用频率硬限制

# 警告和停止消息
_WARNING_MSG = "[LOOP DETECTED] 检测到重复操作，请停止并给出最终回答。"
_HARD_STOP_MSG = "[FORCED STOP] 操作循环超出安全限制，强制停止。"
_TOOL_FREQ_WARNING_MSG = "[LOOP DETECTED] {tool_name} 被调用过于频繁，请停止并给出最终回答。"
_TOOL_FREQ_HARD_STOP_MSG = "[FORCED STOP] {tool_name} 被调用 {count} 次超出安全限制，强制停止。"


def _normalize_tool_call_args(raw_args: Any) -> tuple[dict, str | None]:
    """规范化工具调用参数。

    处理 JSON 字符串等非字典参数。

    Args:
        raw_args: 原始参数

    Returns:
        (规范化后的字典, 回退用的字符串键)
    """
    if isinstance(raw_args, dict):
        return raw_args, None

    if isinstance(raw_args, str):
        try:
            parsed = json.loads(raw_args)
        except (json.JSONDecodeError, TypeError):
            return {}, raw_args

        if isinstance(parsed, dict):
            return parsed, None
        return {}, json.dumps(parsed, sort_keys=True, default=str)

    if raw_args is None:
        return {}, None

    return {}, json.dumps(raw_args, sort_keys=True, default=str)


def _stable_tool_key(name: str, args: dict, fallback_key: str | None) -> str:
    """生成稳定的工具调用标识键。

    对不同类型的工具使用不同的策略：
    - read_file: 按路径桶分组（避免读取相似文件 100 次报警）
    - write_file/str_replace: 包含完整参数（内容敏感）
    - 其他工具: 只保留关键字段

    Args:
        name: 工具名称
        args: 工具参数
        fallback_key: 回退键

    Returns:
        稳定的标识字符串
    """
    if name == "read_file" and fallback_key is None:
        path = args.get("path") or ""
        start_line = args.get("start_line")
        end_line = args.get("end_line")

        # 按行号桶分组（每 200 行为一个桶）
        bucket_size = 200
        try:
            start_bucket = (int(start_line) - 1) // bucket_size if start_line else 0
            end_bucket = (int(end_line) - 1) // bucket_size if end_line else start_bucket
        except (TypeError, ValueError):
            start_bucket = 0
            end_bucket = 0

        return f"{path}:{start_bucket}-{end_bucket}"

    # write_file / str_replace 包含完整参数
    if name in {"write_file", "str_replace"}:
        if fallback_key is not None:
            return fallback_key
        return json.dumps(args, sort_keys=True, default=str)

    # 其他工具只保留关键字段
    salient_fields = ("path", "url", "query", "command", "pattern", "glob", "cmd", "index")
    stable_args = {field: args[field] for field in salient_fields if args.get(field) is not None}
    if stable_args:
        return json.dumps(stable_args, sort_keys=True, default=str)

    if fallback_key is not None:
        return fallback_key

    return json.dumps(args, sort_keys=True, default=str)


def _hash_tool_calls(tool_calls: list[dict]) -> str:
    """计算工具调用序列的哈希值。

    注意：这是顺序无关的哈希（相同调用集合产生相同哈希）。

    Args:
        tool_calls: 工具调用列表

    Returns:
        12 位 MD5 哈希字符串
    """
    normalized: list[str] = []

    for tc in tool_calls:
        name = tc.get("name", "")
        args, fallback_key = _normalize_tool_call_args(tc.get("args", {}))
        key = _stable_tool_key(name, args, fallback_key)
        normalized.append(f"{name}:{key}")

    # 排序使顺序无关
    normalized.sort()
    blob = json.dumps(normalized, sort_keys=True, default=str)
    return hashlib.md5(blob.encode()).hexdigest()[:12]


class LoopDetectionMiddleware(BaseMiddleware):
    """循环检测中间件。

    功能：
    1. Hash 检测：检测完全相同的工具调用序列
    2. 频率检测：检测同一工具类型被调用多次

    使用 LRU 缓存跟踪历史，支持多线程安全。

    配置参数：
    - warn_threshold: 注入警告前的重复次数（默认 3）
    - hard_limit: 强制停止前的重复次数（默认 5）
    - window_size: 滑动窗口大小（默认 20）
    - max_tracked_threads: 最大跟踪线程数（默认 100）
    - tool_freq_warn: 同类型工具频率警告阈值（默认 30）
    - tool_freq_hard_limit: 同类型工具频率硬限制（默认 50）
    """

    name: str = "loop_detection"
    description: str = "检测并阻止重复的工具调用循环"

    def __init__(
        self,
        enabled: bool = True,
        order: int = 10,  # 在 after_model 中执行，需要较晚
        warn_threshold: int = _DEFAULT_WARN_THRESHOLD,
        hard_limit: int = _DEFAULT_HARD_LIMIT,
        window_size: int = _DEFAULT_WINDOW_SIZE,
        max_tracked_threads: int = _DEFAULT_MAX_TRACKED_THREADS,
        tool_freq_warn: int = _DEFAULT_TOOL_FREQ_WARN,
        tool_freq_hard_limit: int = _DEFAULT_TOOL_FREQ_HARD_LIMIT,
    ):
        """初始化循环检测中间件。

        Args:
            enabled: 是否启用
            order: 执行顺序
            warn_threshold: 软限制（警告）
            hard_limit: 硬限制（强制停止）
            window_size: 滑动窗口大小
            max_tracked_threads: 最大跟踪线程数
            tool_freq_warn: 工具频率警告阈值
            tool_freq_hard_limit: 工具频率硬限制
        """
        super().__init__(enabled=enabled, order=order)
        self.warn_threshold = warn_threshold
        self.hard_limit = hard_limit
        self.window_size = window_size
        self.max_tracked_threads = max_tracked_threads
        self.tool_freq_warn = tool_freq_warn
        self.tool_freq_hard_limit = tool_freq_hard_limit

        self._lock = threading.Lock()
        # LRU 历史记录: thread_id -> [call_hash, ...]
        self._history: OrderedDict[str, list[str]] = OrderedDict()
        # 已警告的哈希: thread_id -> set of hash
        self._warned: dict[str, set[str]] = defaultdict(set)
        # 工具频率: thread_id -> {tool_name: count}
        self._tool_freq: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        # 工具频率警告: thread_id -> set of tool_name
        self._tool_freq_warned: dict[str, set[str]] = defaultdict(set)

    def _get_thread_id(self, runtime: dict[str, Any]) -> str:
        """获取线程 ID。"""
        return runtime.get("thread_id", "default")

    def _evict_if_needed(self) -> None:
        """如果超出最大跟踪线程数，驱逐最旧的记录。"""
        while len(self._history) > self.max_tracked_threads:
            evicted_id, _ = self._history.popitem(last=False)
            self._warned.pop(evicted_id, None)
            self._tool_freq.pop(evicted_id, None)
            self._tool_freq_warned.pop(evicted_id, None)
            logger.debug(f"驱逐循环跟踪记录: {evicted_id}")

    def _track_and_check(
        self,
        state: dict[str, Any],
        runtime: dict[str, Any],
    ) -> tuple[str | None, bool]:
        """跟踪并检测循环。

        两层检测：
        1. Hash 检测：相同调用序列
        2. 频率检测：同类型工具调用次数

        Args:
            state: 当前状态
            runtime: 运行时上下文

        Returns:
            (警告消息或None, 是否强制停止)
        """
        messages = state.get("messages", [])
        if not messages:
            return None, False

        last_msg = messages[-1]
        if not isinstance(last_msg, AIMessage):
            return None, False

        tool_calls = getattr(last_msg, "tool_calls", None)
        if not tool_calls:
            return None, False

        thread_id = self._get_thread_id(runtime)
        call_hash = _hash_tool_calls(tool_calls)

        with self._lock:
            # 更新历史
            if thread_id in self._history:
                self._history.move_to_end(thread_id)
            else:
                self._history[thread_id] = []
                self._evict_if_needed()

            history = self._history[thread_id]
            history.append(call_hash)
            if len(history) > self.window_size:
                history[:] = history[-self.window_size:]

            # === 第一层：Hash 检测 ===
            count = history.count(call_hash)
            tool_names = [tc.get("name", "?") for tc in tool_calls]

            if count >= self.hard_limit:
                logger.error(
                    f"循环硬限制触发: thread={thread_id}, hash={call_hash}, "
                    f"count={count}, tools={tool_names}"
                )
                return _HARD_STOP_MSG, True

            if count >= self.warn_threshold:
                warned = self._warned[thread_id]
                if call_hash not in warned:
                    warned.add(call_hash)
                    logger.warning(
                        f"循环警告触发: thread={thread_id}, hash={call_hash}, "
                        f"count={count}, tools={tool_names}"
                    )
                    return _WARNING_MSG, False

            # === 第二层：工具频率检测 ===
            freq = self._tool_freq[thread_id]
            for tc in tool_calls:
                tool_name = tc.get("name", "")
                if not tool_name:
                    continue

                freq[tool_name] += 1
                tc_count = freq[tool_name]

                if tc_count >= self.tool_freq_hard_limit:
                    logger.error(
                        f"工具频率硬限制触发: thread={thread_id}, tool={tool_name}, "
                        f"count={tc_count}"
                    )
                    return _TOOL_FREQ_HARD_STOP_MSG.format(
                        tool_name=tool_name, count=tc_count
                    ), True

                if tc_count >= self.tool_freq_warn:
                    tool_warned = self._tool_freq_warned[thread_id]
                    if tool_name not in tool_warned:
                        tool_warned.add(tool_name)
                        logger.warning(
                            f"工具频率警告: thread={thread_id}, tool={tool_name}, "
                            f"count={tc_count}"
                        )
                        return _TOOL_FREQ_WARNING_MSG.format(tool_name=tool_name), False

        return None, False

    @staticmethod
    def _append_text(content: str | list | None, text: str) -> str | list:
        """追加文本到消息内容。

        处理内容为字符串、列表或 None 的情况。
        """
        if content is None:
            return text
        if isinstance(content, list):
            return [*content, {"type": "text", "text": f"\n\n{text}"}]
        if isinstance(content, str):
            return content + f"\n\n{text}"
        return str(content) + f"\n\n{text}"

    @staticmethod
    def _build_hard_stop_update(last_msg: AIMessage, content: str | list) -> dict:
        """构建硬停止时的消息更新。"""
        update = {
            "tool_calls": [],
            "content": content,
        }

        # 清除 additional_kwargs 中的工具调用信息
        additional_kwargs = dict(getattr(last_msg, "additional_kwargs", {}) or {})
        for key in ("tool_calls", "function_call"):
            additional_kwargs.pop(key, None)
        update["additional_kwargs"] = additional_kwargs

        # 更新响应元数据
        response_metadata = deepcopy(getattr(last_msg, "response_metadata", {}) or {})
        if response_metadata.get("finish_reason") == "tool_calls":
            response_metadata["finish_reason"] = "stop"
        update["response_metadata"] = response_metadata

        return update

    async def after_model(
        self,
        state: dict[str, Any],
        runtime: dict[str, Any],
    ) -> MiddlewareResult | None:
        """在模型调用后检测循环。

        Args:
            state: 当前状态
            runtime: 运行时上下文

        Returns:
            MiddlewareResult 或 None
        """
        warning, hard_stop = self._track_and_check(state, runtime)

        if hard_stop:
            # 强制停止：移除 tool_calls，注入停止消息
            messages = state.get("messages", [])
            if not messages:
                return None

            last_msg = messages[-1]
            if isinstance(last_msg, AIMessage):
                content = self._append_text(last_msg.content, warning or _HARD_STOP_MSG)
                update = self._build_hard_stop_update(last_msg, content)

                # 更新最后一条消息
                updated_messages = list(messages)
                updated_messages[-1] = last_msg.model_copy(update=update)

                return MiddlewareResult(updates={"messages": updated_messages})

            return MiddlewareResult.stopped(warning or _HARD_STOP_MSG)

        if warning:
            # 软限制：注入警告消息
            return MiddlewareResult.with_messages([
                HumanMessage(content=warning, name="loop_warning")
            ])

        return None

    def reset(self, thread_id: str | None = None) -> None:
        """重置跟踪状态。

        Args:
            thread_id: 线程 ID（None 表示重置所有）
        """
        with self._lock:
            if thread_id:
                self._history.pop(thread_id, None)
                self._warned.pop(thread_id, None)
                self._tool_freq.pop(thread_id, None)
                self._tool_freq_warned.pop(thread_id, None)
            else:
                self._history.clear()
                self._warned.clear()
                self._tool_freq.clear()
                self._tool_freq_warned.clear()

            logger.debug(f"重置循环检测状态: thread_id={thread_id or 'all'}")
