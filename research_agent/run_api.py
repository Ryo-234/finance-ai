"""API 服务启动脚本。"""

import argparse
import logging
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
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