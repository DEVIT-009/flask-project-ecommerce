from functools import wraps
from flask import request, redirect, url_for, jsonify, g, render_template, abort
from api.services.auth_service import AuthService


def login_required(f):
    """
    Decorator for protecting admin/dashboard views.
    Redirects unauthenticated browser requests to /login.
    Returns 401 JSON for AJAX/API requests.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        current_user = AuthService.get_current_user()
        if current_user is None:
            # Check if this is an API or AJAX request
            is_ajax = (
                request.headers.get("X-Requested-With") == "XMLHttpRequest"
                or request.is_json
                or "application/json" in request.headers.get("Accept", "")
            )
            if is_ajax:
                return jsonify({"error": "Unauthorized", "message": "Authentication required."}), 401

            # Retain destination URL for redirection after successful login
            next_url = request.full_path if request.query_string else request.path
            # Strip trailing '?' if query string is empty
            if next_url.endswith("?"):
                next_url = next_url[:-1]

            return redirect(url_for("admin_routes.login", next=next_url))

        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """
    Decorator for admin-only views (e.g., Log Management).
    Redirects unauthenticated requests to /login.
    Enforces that current_user.role == 'admin'.
    Returns 403 Forbidden for non-admin users.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        current_user = AuthService.get_current_user()
        is_ajax = (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or request.is_json
            or "application/json" in request.headers.get("Accept", "")
        )
        if current_user is None:
            if is_ajax:
                return jsonify({"error": "Unauthorized", "message": "Authentication required."}), 401

            next_url = request.full_path if request.query_string else request.path
            if next_url.endswith("?"):
                next_url = next_url[:-1]
            return redirect(url_for("admin_routes.login", next=next_url))

        if getattr(current_user, "role", "").lower() != "admin":
            if is_ajax:
                return jsonify({"error": "Forbidden", "message": "Admin privileges required."}), 403
            try:
                return render_template("errors/403.html"), 403
            except Exception:
                abort(403)

        return f(*args, **kwargs)
    return decorated_function


def load_current_user():
    """Before-request hook to populate g.current_user."""
    AuthService.get_current_user()


def auth_context_processor():
    """Template context processor making current_user available in all Jinja templates."""
    return {"current_user": AuthService.get_current_user()}
