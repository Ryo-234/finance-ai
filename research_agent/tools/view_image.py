"""view_image 工具 - 读取图片文件用于视觉理解。"""

import os
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

from langchain_core.tools import tool

# 允许的图片根路径
_ALLOWED_IMAGE_ROOTS = [
    "/tmp/uploads",
    "./uploads",
    os.path.expanduser("~/uploads"),
    "/mnt/user-data/uploads",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads"),
]

# 虚拟路径到实际路径的映射
# Linux风格路径 -> Windows项目目录
_VIRTUAL_PATH_MAPPING = {
    "/mnt/user-data/uploads": os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads"),
}


def _map_virtual_path(image_path: str) -> str:
    """将虚拟路径映射到实际文件系统路径。

    Args:
        image_path: 虚拟路径，如 /mnt/user-data/uploads/xxx.png

    Returns:
        实际文件系统路径
    """
    # 替换虚拟路径为实际路径
    for virtual_root, actual_root in _VIRTUAL_PATH_MAPPING.items():
        if image_path.startswith(virtual_root):
            relative_path = image_path[len(virtual_root):].lstrip('/\\')
            actual_path = os.path.join(actual_root, relative_path)
            return actual_path
    return image_path

_MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20MB
_SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def _is_allowed_path(image_path: str) -> bool:
    """检查路径是否在允许的目录内。"""
    abs_path = os.path.abspath(image_path)
    for root in _ALLOWED_IMAGE_ROOTS:
        abs_root = os.path.abspath(root)
        if abs_path.startswith(abs_root):
            return True
    return False


def _get_mime_type(image_path: str) -> str:
    """根据扩展名获取 MIME 类型。"""
    import mimetypes
    mime_type, _ = mimetypes.guess_type(image_path)
    if mime_type:
        return mime_type
    # 默认
    ext = Path(image_path).suffix.lower()
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    elif ext == ".png":
        return "image/png"
    elif ext == ".gif":
        return "image/gif"
    elif ext == ".webp":
        return "image/webp"
    return "image/jpeg"


@tool("view_image", return_direct=True)
def view_image_tool(
    image_path: str,
) -> str:
    """读取图片文件并准备用于视觉理解。

    当用户发送了图片或需要分析图片内容时使用此工具。

    Args:
        image_path: 图片文件的绝对路径，支持 jpg/jpeg/png/gif/webp 格式

    Returns:
        图片读取结果，包含路径和 MIME 类型
    """
    path = Path(image_path)

    # 检查路径是否存在
    if not path.exists():
        return f"错误：图片文件不存在: {image_path}"

    # 检查是否是文件
    if not path.is_file():
        return f"错误：路径不是文件: {image_path}"

    # 检查扩展名
    if path.suffix.lower() not in _SUPPORTED_FORMATS:
        return f"错误：不支持的图片格式。支持的格式: {', '.join(_SUPPORTED_FORMATS)}"

    # 检查文件大小
    try:
        size = path.stat().st_size
        if size > _MAX_IMAGE_BYTES:
            return f"错误：图片文件太大 ({size} bytes)。最大支持 20MB"
        if size == 0:
            return f"错误：图片文件为空: {image_path}"
    except OSError as e:
        return f"错误：无法读取文件信息: {str(e)}"

    # 获取 MIME 类型
    mime_type = _get_mime_type(image_path)

    # 返回成功信息（实际 base64 编码由中间件处理）
    return f"已读取图片: {image_path} ({mime_type}, {size} bytes)"


def read_image_as_base64(image_path: str) -> tuple[str, str]:
    """读取图片并返回 base64 编码和 MIME 类型。

    Args:
        image_path: 图片文件路径（支持虚拟路径）

    Returns:
        (base64 编码字符串, MIME 类型)
    """
    import base64

    # 映射虚拟路径到实际路径
    actual_path = _map_virtual_path(image_path)
    path = Path(actual_path)
    mime_type = _get_mime_type(image_path)

    with open(path, "rb") as f:
        data = f.read()
        base64_data = base64.b64encode(data).decode("utf-8")

    return base64_data, mime_type
