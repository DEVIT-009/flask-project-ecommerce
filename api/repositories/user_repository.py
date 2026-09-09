from typing import Optional, List
from extensions import db
from api.models.user import User


class UserRepository:
    @staticmethod
    def get_by_id(user_id: int) -> Optional[User]:
        return db.session.get(User, user_id)

    @staticmethod
    def get_by_email(email: str) -> Optional[User]:
        if not email:
            return None
        return User.query.filter(User.email.ilike(email.strip())).first()

    @staticmethod
    def get_by_identifier(identifier: str) -> Optional[User]:
        if not identifier:
            return None
        cleaned = identifier.strip()
        user = User.query.filter(User.email.ilike(cleaned)).first()
        if not user:
            user = User.query.filter(User.name.ilike(cleaned)).first()
        return user

    @staticmethod
    def get_all() -> List[User]:
        return User.query.order_by(User.id.asc()).all()

    @staticmethod
    def save(user: User) -> User:
        db.session.add(user)
        db.session.commit()
        return user

    @staticmethod
    def delete(user: User) -> None:
        db.session.delete(user)
        db.session.commit()
