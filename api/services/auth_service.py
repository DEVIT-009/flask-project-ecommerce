import time
from typing import Optional, Tuple
from flask import session, g
from extensions import db
from api.models.user import User
from api.repositories.user_repository import UserRepository
from werkzeug.security import check_password_hash, generate_password_hash


# Dummy hash to prevent timing attack enumeration
_DUMMY_HASH = generate_password_hash("dummy-timing-defense-pass")


class AuthService:
    @staticmethod
    def authenticate(identifier: str, password: str) -> Tuple[Optional[User], Optional[str]]:
        if not identifier or not password:
            return None, "Please enter both username/email and password."

        user = UserRepository.get_by_identifier(identifier)

        if not user:
            # Timing mitigation
            check_password_hash(_DUMMY_HASH, password)
            return None, "Invalid email/username or password."

        if not user.check_password(password):
            return None, "Invalid email/username or password."

        if not user.is_active:
            return None, "Your account has been deactivated. Please contact an administrator."

        # Transparent upgrade of legacy plain-text password to hash
        if user.password == password:
            try:
                user.set_password(password)
                db.session.commit()
            except Exception:
                db.session.rollback()

        return user, None

    @staticmethod
    def login_user(user: User, remember: bool = False) -> None:
        """
        Establish authenticated session for user.
        Clears previous session data to prevent session fixation.
        """
        session.clear()
        session["user_id"] = user.id
        session["user_name"] = user.name
        session["user_email"] = user.email
        session["user_role"] = user.role
        session["_login_time"] = int(time.time())
        session.permanent = bool(remember)
        g.current_user = user

    @staticmethod
    def logout_user() -> None:
        """Clear the current session and unbind current user."""
        session.clear()
        g.current_user = None

    @staticmethod
    def get_current_user() -> Optional[User]:
        """
        Retrieve the currently authenticated User from flask.g or session.
        Caches result in flask.g for the duration of the request.
        """
        if hasattr(g, "current_user") and g.current_user is not None:
            return g.current_user

        user_id = session.get("user_id")
        if not user_id:
            g.current_user = None
            return None

        user = UserRepository.get_by_id(user_id)
        if not user or not user.is_active:
            # Session exists for invalid/deleted/inactive user -> invalidate
            session.clear()
            g.current_user = None
            return None

        g.current_user = user
        return user
