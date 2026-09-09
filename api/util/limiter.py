from flask import session, g, request
from flask_limiter.util import get_remote_address


def get_user_id_or_ip() -> str:
    """
    Rate limit key function for authenticated users.
    
    Returns:
        - 'user:<user_id>' if the request is from an authenticated user (via session or g.current_user).
        - '<ip_address>' if the request is unauthenticated.
    """
    # Check session user_id
    user_id = session.get("user_id")
    if user_id is not None:
        return f"user:{user_id}"

    # Check g._current_user
    current_user = getattr(g, "_current_user", None)
    if current_user and hasattr(current_user, "id") and current_user.id is not None:
        return f"user:{current_user.id}"

    # Fallback to client remote IP address
    return get_remote_address()


def get_client_ip() -> str:
    """Return the client IP address using Flask-Limiter utility."""
    return get_remote_address()
