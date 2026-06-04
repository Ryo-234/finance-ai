"""支付宝集成 —— 沙箱环境 + PC 网站扫码支付。

加载顺序（优先级从高到低）：
1. .pem 文件（推荐）：ALIPAY_PRIVATE_KEY_PATH + ALIPAY_PUBLIC_KEY_PATH
2. .env 字符串：ALIPAY_APP_PRIVATE_KEY + ALIPAY_PUBLIC_KEY（必须是 PEM 格式）

环境变量：
- ALIPAY_APPID: 沙箱 appid
- ALIPAY_APP_PRIVATE_KEY 或 ALIPAY_PRIVATE_KEY_PATH: 应用私钥
- ALIPAY_PUBLIC_KEY 或 ALIPAY_PUBLIC_KEY_PATH: 支付宝公钥
- ALIPAY_NOTIFY_URL: 异步通知地址（需公网可访问，ngrok）
- ALIPAY_RETURN_URL: 同步跳转地址
- ALIPAY_GATEWAY: 网关 URL（沙箱：https://openapi.alipaydev.com/gateway.do）
- ALIPAY_DEBUG: True=沙箱，False=正式
"""

import io
import logging
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import qrcode
from alipay import AliPay

logger = logging.getLogger(__name__)


@dataclass
class AlipayConfig:
    """支付宝配置。"""

    appid: str
    app_private_key: str
    alipay_public_key: str
    notify_url: str
    return_url: str
    gateway: str = "https://openapi.alipaydev.com/gateway.do"
    debug: bool = True

    @classmethod
    def from_env(cls) -> "AlipayConfig":
        """从环境变量加载配置（优先从 .pem 文件加载密钥）。"""
        debug = os.getenv("ALIPAY_DEBUG", "true").lower() == "true"

        # 优先从 .pem 文件加载（避免 .env 多行字符串问题）
        priv_path = os.getenv("ALIPAY_PRIVATE_KEY_PATH", "")
        pub_path = os.getenv("ALIPAY_PUBLIC_KEY_PATH", "")

        app_private_key = ""
        if priv_path and Path(priv_path).exists():
            app_private_key = Path(priv_path).read_text(encoding="utf-8").strip()
            logger.info(f"从文件加载应用私钥: {priv_path}")
        else:
            app_private_key = os.getenv("ALIPAY_APP_PRIVATE_KEY", "")

        alipay_public_key = ""
        if pub_path and Path(pub_path).exists():
            alipay_public_key = Path(pub_path).read_text(encoding="utf-8").strip()
            logger.info(f"从文件加载支付宝公钥: {pub_path}")
        else:
            alipay_public_key = os.getenv("ALIPAY_PUBLIC_KEY", "")

        return cls(
            appid=os.getenv("ALIPAY_APPID", ""),
            app_private_key=app_private_key,
            alipay_public_key=alipay_public_key,
            notify_url=os.getenv("ALIPAY_NOTIFY_URL", ""),
            return_url=os.getenv("ALIPAY_RETURN_URL", ""),
            gateway=os.getenv(
                "ALIPAY_GATEWAY",
                "https://openapi.alipaydev.com/gateway.do" if debug
                else "https://openapi.alipay.com/gateway.do",
            ),
            debug=debug,
        )

    def is_configured(self) -> bool:
        return bool(self.appid and self.app_private_key and self.alipay_public_key)


class AlipayClient:
    """支付宝客户端封装。

    提供：
    - create_pc_pay_url(): 生成 PC 网站支付链接（前端转二维码）
    - verify_notify(): 验证异步通知签名
    - query_order(): 查询订单状态
    - refund(): 发起退款
    - generate_qr_code(): 生成二维码图片（PNG bytes）
    """

    def __init__(self, config: Optional[AlipayConfig] = None):
        self.config = config or AlipayConfig.from_env()
        self._client: Optional[AliPay] = None

    @property
    def client(self) -> AliPay:
        if self._client is None:
            if not self.config.is_configured():
                raise ValueError(
                    "支付宝未配置：请在 .env 中设置 ALIPAY_APPID/ALIPAY_APP_PRIVATE_KEY/ALIPAY_PUBLIC_KEY"
                )
            self._client = AliPay(
                appid=self.config.appid,
                app_notify_url=self.config.notify_url,
                app_private_key_string=self.config.app_private_key,
                alipay_public_key_string=self.config.alipay_public_key,
                sign_type="RSA2",
            )
        return self._client

    def create_pc_pay_url(self, order_no: str, amount: str, subject: str) -> str:
        """生成 PC 网站支付链接（前端用此 URL 生成二维码）。

        Args:
            order_no: 商户订单号
            amount: 金额（元，字符串，最多 2 位小数）
            subject: 订单标题

        Returns:
            支付 URL（前端用 qrcode 库转二维码）
        """
        url = self.client.api_alipay_trade_page_pay(
            out_trade_no=order_no,
            total_amount=amount,
            subject=subject,
            return_url=self.config.return_url,
            notify_url=self.config.notify_url,
        )
        # 拼接完整 URL
        if url.startswith("http"):
            return url
        return f"{self.config.gateway}?{url}"

    def verify_notify(self, data: dict) -> bool:
        """验证异步通知签名。"""
        try:
            return self.client.verify(data, self.config.alipay_public_key)
        except Exception as e:
            logger.error(f"支付宝通知验签失败: {e}")
            return False

    def query_order(self, order_no: str) -> dict:
        """查询订单状态。"""
        return self.client.api_alipay_trade_query(out_trade_no=order_no)

    def refund(self, order_no: str, refund_amount: str, reason: str = "用户退款") -> dict:
        """发起退款。

        Args:
            order_no: 原商户订单号
            refund_amount: 退款金额（元）
            reason: 退款原因

        Returns:
            支付宝返回的退款结果
        """
        out_request_no = f"RF{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(3).upper()}"
        result = self.client.api_alipay_trade_refund(
            out_trade_no=order_no,
            refund_amount=refund_amount,
            refund_reason=reason,
            out_request_no=out_request_no,
        )
        result["out_request_no"] = out_request_no
        return result


def generate_qr_code(data: str, box_size: int = 10, border: int = 2) -> bytes:
    """生成二维码图片（PNG bytes）。"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# 全局单例
_alipay_client: Optional[AlipayClient] = None


def get_alipay_client() -> AlipayClient:
    """获取支付宝客户端单例。"""
    global _alipay_client
    if _alipay_client is None:
        _alipay_client = AlipayClient()
    return _alipay_client
