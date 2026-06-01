"""用户数据仓库。"""

from sqlalchemy.orm import Session
from db.models import User


class UserRepo:
    """用户 CRUD 操作。"""

    def __init__(self, session: Session):
        self.session = session

    def create(self, email: str, hashed_password: str, display_name: str = "") -> User:
        user = User(
            email=email,
            hashed_password=hashed_password,
            display_name=display_name or email.split("@")[0],
        )
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def get_by_id(self, user_id: str) -> User | None:
        return self.session.query(User).filter(User.id == user_id).first()

    def get_by_email(self, email: str) -> User | None:
        return self.session.query(User).filter(User.email == email).first()

    def update_plan(self, user_id: str, plan_type: str, expires_at=None) -> User | None:
        user = self.get_by_id(user_id)
        if user:
            user.plan_type = plan_type
            if expires_at:
                user.plan_expires_at = expires_at
            self.session.commit()
            self.session.refresh(user)
        return user

    def update_profile(self, user_id: str, display_name: str = None) -> User | None:
        user = self.get_by_id(user_id)
        if user:
            if display_name is not None:
                user.display_name = display_name
            self.session.commit()
            self.session.refresh(user)
        return user
