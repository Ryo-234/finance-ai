"""订阅服务 —— 处理支付成功后的用户升级/续费逻辑。"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from db.models import User
from db.repositories.subscription_repo import SubscriptionRepo
from db.repositories.user_repo import UserRepo

logger = logging.getLogger(__name__)


class SubscriptionService:
    """订阅业务逻辑。

    核心职责：
    - 支付成功后激活订阅
    - 更新用户 plan_type 和 plan_expires_at
    - 处理续费（在原 expires_at 基础上累加）
    """

    def __init__(self, session: Session):
        self.session = session
        self.sub_repo = SubscriptionRepo(session)
        self.user_repo = UserRepo(session)

    def activate(
        self,
        user_id: str,
        plan_type: str,
        billing_cycle: str,
        order_no: str = "",
    ) -> Optional[User]:
        """支付成功后激活订阅。

        逻辑：
        1. 查询用户当前订阅
        2. 计算新 expires_at（在原 expires_at 基础上累加，或从 now 开始）
        3. 创建新的 Subscription 记录
        4. 更新 User.plan_type 和 User.plan_expires_at
        """
        user = self.user_repo.get_by_id(user_id)
        if not user:
            logger.error(f"用户不存在: {user_id}")
            return None

        # 计算新到期时间：原订阅未过期则续期，否则从 now 开始
        current_sub = self.sub_repo.get_current(user_id)
        if current_sub and current_sub.expires_at > datetime.now(timezone.utc):
            base = current_sub.expires_at
        else:
            base = datetime.now(timezone.utc)

        if billing_cycle == "yearly":
            new_expires = base + timedelta(days=365)
        else:  # monthly
            new_expires = base + timedelta(days=30)

        # 创建订阅记录
        self.sub_repo.create(
            user_id=user_id,
            plan_type=plan_type,
            billing_cycle=billing_cycle,
            expires_at=new_expires,
            order_no=order_no,
        )

        # 更新 User 表
        self.user_repo.update_plan(user_id, plan_type, new_expires)

        logger.info(
            f"订阅已激活: user={user_id} plan={plan_type} cycle={billing_cycle} "
            f"expires_at={new_expires.isoformat()}"
        )
        return self.user_repo.get_by_id(user_id)

    def cancel(self, user_id: str) -> Optional[User]:
        """用户主动取消订阅（关闭自动续费，到期后降级到 free）。"""
        current_sub = self.sub_repo.get_current(user_id)
        if not current_sub:
            return None
        self.sub_repo.cancel(current_sub.id)
        logger.info(f"用户已取消订阅: user={user_id} sub_id={current_sub.id}")
        # 立即降级到 free（如果用户希望保留到到期，请修改此处逻辑）
        self.user_repo.update_plan(user_id, "free", None)
        return self.user_repo.get_by_id(user_id)
