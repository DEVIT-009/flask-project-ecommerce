from extensions import csrf
from api import api_routes
from flask import Flask, render_template, request, jsonify
from config import Config
from extensions import db, migrate, limiter

from admin import admin_routes
from web import web_routes
from api.util.auth import load_current_user, auth_context_processor
from api.services.log_service import LogService

app = Flask(__name__)
app.config.from_object(Config)
csrf.init_app(app)
cors.init_app(app)

db.init_app(app)
migrate.init_app(app, db)
limiter.init_app(app)

# import models AFTER db init
import api.models  # noqa: E402, F401

# Register auth hooks
app.before_request(load_current_user)
app.context_processor(auth_context_processor)

# Register blueprints
app.register_blueprint(web_routes, url_prefix='')
app.register_blueprint(api_routes, url_prefix='/api/v1')
app.register_blueprint(admin_routes, url_prefix='/admin')


# ─── Error Handlers ────────────────────────────────────────────────────────────
@app.errorhandler(429)
def handle_rate_limit_exceeded(e):
    LogService.log(
        action="RATE_LIMIT",
        module="RATE_LIMIT",
        severity="WARNING",
        status_code=429,
        description=f"Rate limit exceeded on {request.method} {request.path}: {getattr(e, 'description', 'Too many requests')}",
    )

    is_ajax = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.is_json
        or "application/json" in request.headers.get("Accept", "")
    )
    if is_ajax:
        return jsonify({
            "error": "Too Many Requests",
            "message": "Rate limit exceeded. Please wait a moment before trying again.",
            "detail": getattr(e, "description", None),
        }), 429

    return render_template(
        "errors/429.html",
        error=e,
        error_description=getattr(e, "description", None),
        retry_after=getattr(e, "retry_after", 60),
    ), 429


@app.errorhandler(403)
def handle_forbidden(e):
    is_ajax = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.is_json
        or "application/json" in request.headers.get("Accept", "")
    )
    if is_ajax:
        return jsonify({"error": "Forbidden", "message": "Admin privileges required."}), 403

    return render_template("errors/403.html"), 403


@app.errorhandler(500)
def handle_internal_server_error(e):
    LogService.log(
        action="ERROR",
        module="SYSTEM",
        severity="ERROR",
        status_code=500,
        description=f"Unhandled internal server error on {request.method} {request.path}",
    )
    is_ajax = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.is_json
        or "application/json" in request.headers.get("Accept", "")
    )
    if is_ajax:
        return jsonify({"error": "Internal Server Error", "message": "An unexpected error occurred."}), 500

    return render_template("errors/500.html"), 500


@app.route("/429")
def rate_limit_page():
    return render_template("errors/429.html", retry_after=60), 429

@app.cli.command("seed")
def seed():
    from seed import seed_admin
    seed_admin()

if __name__ == "__main__":
    app.run(debug=True)