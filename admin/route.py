import logging
from flask import render_template, request, jsonify, redirect, url_for, flash
from werkzeug.security import generate_password_hash
from . import admin_routes
from extensions import db, limiter
from flask_limiter.util import get_remote_address
from api.models.user import User
from api.services.auth_service import AuthService
from api.util.auth import login_required, admin_required
from api.util.file_upload import save_profile_image, delete_profile_image
from api.util.limiter import get_user_id_or_ip
from api.services.log_service import LogService

logger = logging.getLogger(__name__)

LOGIN_LIMIT = "5 per minute"
ADMIN_LIMIT = "10 per minute"

def _is_safe_redirect(url: str) -> bool:
    if not url:
        return False
    return url.startswith("/") and not url.startswith("//") and not url.startswith("/\\")

@admin_routes.route("/login", methods=["GET", "POST"])
@limiter.limit(LOGIN_LIMIT, key_func=get_remote_address)
def login():
    if AuthService.get_current_user() is not None:
        next_url = request.args.get("next")
        if next_url and _is_safe_redirect(next_url):
            return redirect(next_url)
        return redirect(url_for("admin_routes.dashboard"))

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))
        next_param = request.form.get("next", "") or request.args.get("next", "")

        user, error = AuthService.authenticate(identifier, password)
        if error:
            LogService.log(
                action="LOGIN",
                module="AUTH",
                severity="WARNING",
                status_code=401,
                description=f"Failed login attempt for identifier: {identifier} - {error}",
                request_data={"identifier": identifier},
            )
            flash(error, "error")
            return render_template(
                "admin/auth/login.html",
                error=error,
                identifier=identifier,
                next=next_param,
            ), 401

        AuthService.login_user(user, remember=remember)
        LogService.log(
            action="LOGIN",
            module="AUTH",
            severity="INFO",
            status_code=200,
            user_id=user.id,
            description=f"User {user.name} ({user.email}) logged in successfully.",
            request_data={"identifier": identifier},
        )
        flash(f"Welcome back, {user.name}!", "success")

        if next_param and _is_safe_redirect(next_param):
            return redirect(next_param)
        return redirect(url_for("admin_routes.dashboard"))

    next_url = request.args.get("next", "")
    return render_template("admin/auth/login.html", next=next_url)

@admin_routes.route("/logout", methods=["GET", "POST"])
@limiter.exempt
def logout():
    current_user = AuthService.get_current_user()
    user_id = current_user.id if current_user else None
    user_name = current_user.name if current_user else "Unknown"

    AuthService.logout_user()

    LogService.log(
        action="LOGOUT",
        module="AUTH",
        severity="INFO",
        status_code=200,
        user_id=user_id,
        description=f"User {user_name} logged out.",
    )
    flash("You have been signed out successfully.", "info")
    return redirect(url_for("admin_routes.login"))



# ─── Admin Root Redirect ───────────────────────────────────────────────────────
@admin_routes.get("")
@admin_routes.get("/")
@limiter.limit(ADMIN_LIMIT, key_func=get_user_id_or_ip)
def admin_root():
    return redirect(url_for("admin_routes.dashboard"))


# ─── Dashboard ─────────────────────────────────────────────────────────────────
@admin_routes.get("/dashboard")
@login_required
@limiter.limit(ADMIN_LIMIT, key_func=get_user_id_or_ip)
def dashboard():
    return render_template("admin/layouts/dashboard.html")


# ─── Users — List page ─────────────────────────────────────────────────────────
@admin_routes.get("/users")
@login_required
@limiter.limit(ADMIN_LIMIT, key_func=get_user_id_or_ip)
def users():
    all_users = User.query.order_by(User.id.asc()).all()
    return render_template("admin/layouts/users.html", users=all_users)


# ─── Users — Create ────────────────────────────────────────────────────────────
@admin_routes.post("/users")
@login_required
@limiter.limit(ADMIN_LIMIT, key_func=get_user_id_or_ip)
def create_user():
    # Handle both multipart/form-data and json
    is_form = bool(request.form)
    data = request.form if is_form else (request.get_json(silent=True) or {})

    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    role = data.get("role", "staff").strip()
    password = data.get("password", "").strip()

    if not name or not email or not password:
        return jsonify({"error": "Name, email, and password are required."}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already exists."}), 409

    saved_profile_image = None
    # Check for uploaded profile image
    if "profile" in request.files and request.files["profile"].filename:
        file = request.files["profile"]
        saved_filename, err = save_profile_image(file)
        if err:
            return jsonify({"error": err}), 400
        saved_profile_image = saved_filename

    user = User(
        name=name,
        email=email,
        role=role,
        password=generate_password_hash(password),
        profile=saved_profile_image,
    )

    try:
        db.session.add(user)
        db.session.commit()

        # Audit log CREATE_USER (INFO)
        LogService.log(
            action="CREATE_USER",
            module="USERS",
            severity="INFO",
            status_code=201,
            description=f"Created user {user.name} ({user.email}) with role '{user.role}' (ID: {user.id})",
            request_data={"name": name, "email": email, "role": role},
            response_data=user.to_dict(),
        )

        # Audit log UPLOAD_IMAGE if profile was uploaded
        if saved_profile_image:
            LogService.log(
                action="UPLOAD_IMAGE",
                module="USERS",
                severity="INFO",
                status_code=201,
                description=f"Uploaded profile image for user {user.name} (ID: {user.id})",
                request_data={"user_id": user.id, "image": saved_profile_image},
            )

        return jsonify(user.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        # Clean up newly uploaded image if database insert fails
        if saved_profile_image:
            delete_profile_image(saved_profile_image)
        logger.error(f"Error creating user: {e}")
        return jsonify({"error": "Database error while creating user."}), 500


# ─── Users — Fetch single (for edit modal) ─────────────────────────────────────
@admin_routes.get("/users/<int:user_id>")
@login_required
@limiter.limit(ADMIN_LIMIT, key_func=get_user_id_or_ip)
def get_user(user_id):
    user = db.get_or_404(User, user_id)
    return jsonify(user.to_dict())


# ─── Users — Update ────────────────────────────────────────────────────────────
@admin_routes.route("/users/<int:user_id>", methods=["PUT", "POST"])
@login_required
@limiter.limit(ADMIN_LIMIT, key_func=get_user_id_or_ip)
def update_user(user_id):
    user = db.get_or_404(User, user_id)

    is_form = bool(request.form)
    data = request.form if is_form else (request.get_json(silent=True) or {})

    name = data.get("name", user.name).strip()
    email = data.get("email", user.email).strip()
    role = data.get("role", user.role)

    if not name or not email:
        return jsonify({"error": "Name and email cannot be empty."}), 400

    # Check email uniqueness (excluding self)
    existing = User.query.filter_by(email=email).first()
    if existing and existing.id != user_id:
        return jsonify({"error": "Email already exists."}), 409

    user.name = name
    user.email = email
    user.role = role

    new_password = data.get("password", "").strip()
    if new_password:
        user.password = generate_password_hash(new_password)

    # Profile image update handling
    old_profile_image = user.profile
    new_profile_image = None
    remove_profile = str(data.get("remove_profile", "")).lower() in ("true", "1", "yes")

    if remove_profile:
        # Case 4: Explicit remove image
        user.profile = None
    elif "profile" in request.files and request.files["profile"].filename:
        # Case 2: New image uploaded
        file = request.files["profile"]
        saved_filename, err = save_profile_image(file)
        if err:
            return jsonify({"error": err}), 400
        new_profile_image = saved_filename
        user.profile = new_profile_image
    # Case 1: No new image and no remove flag -> keep existing user.profile

    try:
        db.session.commit()
        # Post-commit cleanup & audit logs:
        if remove_profile and old_profile_image:
            delete_profile_image(old_profile_image)
            LogService.log(
                action="REMOVE_IMAGE",
                module="USERS",
                severity="INFO",
                status_code=200,
                description=f"Removed profile image for user {user.name} (ID: {user.id})",
                request_data={"user_id": user.id},
            )
        elif new_profile_image and old_profile_image:
            delete_profile_image(old_profile_image)
            LogService.log(
                action="UPLOAD_IMAGE",
                module="USERS",
                severity="INFO",
                status_code=200,
                description=f"Updated profile image for user {user.name} (ID: {user.id})",
                request_data={"user_id": user.id, "image": new_profile_image},
            )
        elif new_profile_image and not old_profile_image:
            LogService.log(
                action="UPLOAD_IMAGE",
                module="USERS",
                severity="INFO",
                status_code=200,
                description=f"Uploaded profile image for user {user.name} (ID: {user.id})",
                request_data={"user_id": user.id, "image": new_profile_image},
            )

        # Audit log UPDATE_USER (INFO)
        LogService.log(
            action="UPDATE_USER",
            module="USERS",
            severity="INFO",
            status_code=200,
            description=f"Updated user {user.name} ({user.email}, ID: {user.id})",
            request_data={"name": name, "email": email, "role": role},
            response_data=user.to_dict(),
        )

        return jsonify(user.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        # If DB update fails, remove newly uploaded image
        if new_profile_image:
            delete_profile_image(new_profile_image)
        logger.error(f"Error updating user {user_id}: {e}")
        return jsonify({"error": "Database error while updating user."}), 500


# ─── Users — Delete ────────────────────────────────────────────────────────────
@admin_routes.delete("/users/<int:user_id>")
@login_required
@limiter.limit(ADMIN_LIMIT, key_func=get_user_id_or_ip)
def delete_user(user_id):
    user = db.get_or_404(User, user_id)
    profile_image_to_delete = user.profile
    user_name = user.name
    user_email = user.email
    user_target_id = user.id

    try:
        db.session.delete(user)
        db.session.commit()
        # Clean up profile image after DB delete succeeds
        if profile_image_to_delete:
            delete_profile_image(profile_image_to_delete)

        # Audit log DELETE_USER (INFO)
        LogService.log(
            action="DELETE_USER",
            module="USERS",
            severity="INFO",
            status_code=200,
            description=f"Deleted user {user_name} ({user_email}, ID: {user_target_id})",
            request_data={"user_id": user_target_id, "name": user_name, "email": user_email},
            response_data={"message": "User deleted successfully."},
        )

        return jsonify({"message": "User deleted successfully."}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting user {user_id}: {e}")
        return jsonify({"error": "Database error while deleting user."}), 500


# ─── Logs — List view & AJAX query ─────────────────────────────────────────────
@admin_routes.get("/logs")
@admin_required
@limiter.limit(ADMIN_LIMIT, key_func=get_user_id_or_ip)
def logs_view():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    q = request.args.get("q", "").strip() or request.args.get("query", "").strip()
    severity = request.args.get("severity", "").strip()
    action = request.args.get("action", "").strip()
    module = request.args.get("module", "").strip()
    method = request.args.get("method", "").strip()
    status_code = request.args.get("status_code", "").strip()
    user_id = request.args.get("user_id", type=int)
    from_date = request.args.get("from_date", "").strip()
    to_date = request.args.get("to_date", "").strip()

    items, total, meta = LogService.get_logs(
        page=page,
        per_page=per_page,
        query=q,
        severity=severity,
        action=action,
        module=module,
        method=method,
        status_code=status_code,
        user_id=user_id,
        from_date=from_date,
        to_date=to_date,
    )

    is_ajax = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.args.get("format") == "json"
        or "application/json" in request.headers.get("Accept", "")
    )

    if is_ajax:
        return jsonify({
            "logs": [log.to_dict() for log in items],
            "total": total,
            "meta": meta,
        })

    stats = LogService.get_stats()
    all_users = User.query.order_by(User.name.asc()).all()

    filters = {
        "q": q,
        "severity": severity,
        "action": action,
        "module": module,
        "method": method,
        "status_code": status_code,
        "user_id": user_id,
        "from_date": from_date,
        "to_date": to_date,
        "per_page": per_page,
    }

    return render_template(
        "admin/layouts/logs.html",
        logs=items,
        total=total,
        meta=meta,
        stats=stats,
        users=all_users,
        filters=filters,
    )


# ─── Logs — Single detail (for modal JSON viewer) ──────────────────────────────
@admin_routes.get("/logs/<int:log_id>")
@admin_required
@limiter.limit(ADMIN_LIMIT, key_func=get_user_id_or_ip)
def get_log_detail(log_id):
    log_entry = LogService.get_log_by_id(log_id)
    if not log_entry:
        return jsonify({"error": "Log not found."}), 404
    return jsonify(log_entry.to_dict())


# ─── Logs — Delete single log ──────────────────────────────────────────────────
@admin_routes.delete("/logs/<int:log_id>")
@admin_required
@limiter.limit(ADMIN_LIMIT, key_func=get_user_id_or_ip)
def delete_single_log(log_id):
    success = LogService.delete_log(log_id)
    if not success:
        return jsonify({"error": "Log not found or could not be deleted."}), 404
    return jsonify({"message": "Log deleted successfully."}), 200


# ─── Logs — Clear / Bulk cleanup ──────────────────────────────────────────────
@admin_routes.post("/logs/clear")
@admin_required
@limiter.limit(ADMIN_LIMIT, key_func=get_user_id_or_ip)
def clear_all_logs():
    data = request.get_json(silent=True) or request.form or {}
    days_val = data.get("days")
    days = None
    if days_val is not None and str(days_val).strip() != "" and str(days_val).lower() != "all":
        try:
            days = int(days_val)
        except ValueError:
            days = None

    deleted_count = LogService.clear_logs(days=days)

    LogService.log(
        action="DELETE_LOGS",
        module="LOGS",
        severity="WARNING",
        description=f"Admin cleared {deleted_count} logs (older than {days} days)" if days else f"Admin cleared all {deleted_count} logs",
    )

    is_ajax = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.is_json
        or "application/json" in request.headers.get("Accept", "")
    )
    if is_ajax:
        return jsonify({"message": f"Successfully deleted {deleted_count} log entries.", "count": deleted_count}), 200

    flash(f"Successfully deleted {deleted_count} log entries.", "success")
    return redirect(url_for("admin_routes.logs_view"))