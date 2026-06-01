"""API 服务启动脚本。"""

import argparse
import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()


class JsonFormatter(logging.Formatter):
    """JSON 格式日志（用于文件输出）。"""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # 附加 X-Request-ID（如果存在）
        req_id = getattr(record, "request_id", None)
        if req_id:
            entry["request_id"] = req_id
        if record.exc_info and record.exc_info[1]:
            entry["error"] = str(record.exc_info[1])
        return json.dumps(entry, ensure_ascii=False)


def _setup_logging(log_level: str = "INFO"):
    """配置双输出日志：控制台文本 + 文件 JSON。

    参数：
        log_level: 日志级别
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    root.handlers.clear()

    # 控制台：可读文本格式
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    ))
    root.addHandler(console)

    # 文件：JSON 格式，轮转（10MB × 5）
    file_handler = RotatingFileHandler(
        "server.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JsonFormatter())
    root.addHandler(file_handler)


_setup_logging()
logger = logging.getLogger(__name__)


def main():
    """启动 API 服务。"""
    parser = argparse.ArgumentParser(description="Research Agent API Server")
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="服务监听地址 (默认: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="服务监听端口 (默认: 8001)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="启用热重载 (开发模式)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="日志级别",
    )

    args = parser.parse_args()

    # 设置日志级别
    logging.getLogger().setLevel(args.log_level.upper())

    logger.info("=" * 60)
    logger.info("Research Agent API Gateway")
    logger.info("=" * 60)
    logger.info(f"监听地址: {args.host}:{args.port}")
    logger.info(f"API 文档: http://{args.host}:{args.port}/docs")
    logger.info(f"健康检查: http://{args.host}:{args.port}/api/health")
    logger.info("=" * 60)

    # 导入 uvicorn 并启动
    import uvicorn
    from api.app import app

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()