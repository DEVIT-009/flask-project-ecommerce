import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, Tuple, List
from flask import request, session, g, has_request_context
from flask_limiter.util import get_remote_address

from extensions import db
from api.models.log import Log

logger = logging.getLogger(__name__)

# Keys that must be redacted for security and compliance
SENSITIVE_KEYS = {
    "password",
    "passwd",
    "pwd",
    "new_password",
    "confirm_password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "auth",
    "cookie",
    "session",
    "csrf_token",
    "credit_card",
    "cvv",
}

# Cache for rate-limit debounce (prevents log flooding on rapid rejections)
_recent_rate_limits: dict = {}


def redact_sensitive_data(data: Any) -> Any:
    """
    Recursively sanitize dictionaries, lists, and primitives
    by masking sensitive credential fields.
    """
    if data is None:
        return None

    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            key_lower = str(key).lower()
            if any(sensitive in key_lower for sensitive in SENSITIVE_KEYS):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, (dict, list)):
                sanitized[key] = redact_sensitive_data(value)
            elif hasattr(value, "filename"):  # FileStorage object
                sanitized[key] = f"[File: {getattr(value, 'filename', 'unknown')}]"
            else:
                sanitized[key] = value
        return sanitized

    if isinstance(data, list):
        return [redact_sensitive_data(item) for item in data]

    if isinstance(data, str):
        # Try parsing JSON string if applicable
        try:
            parsed = json.loads(data)
            if isinstance(parsed, (dict, list)):
                return redact_sensitive_data(parsed)
        except (ValueError, TypeError):
            pass
        return data

    return data


def serialize_payload(payload: Any) -> Optional[str]:
    """
    Safely redact and serialize request or response data to JSON.
    Returns None when payload is empty or unavailable.
    """
    if payload is None:
        return None

    try:
        sanitized = redact_sensitive_data(payload)
        if sanitized is None or (isinstance(sanitized, (dict, list)) and len(sanitized) == 0):
            return None
        return json.dumps(sanitized, default=str, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Could not serialize log payload: {e}")
        return str(payload)


class LogService:
    @staticmethod
    def log(
        action: str,
        module: str,
        severity: str = "INFO",
        description: Optional[str] = None,
        user_id: Optional[int] = None,
        method: Optional[str] = None,
        endpoint: Optional[str] = None,
        status_code: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_data: Optional[Any] = None,
        response_data: Optional[Any] = None,
        skip_rate_limit_debounce: bool = False,
    ) -> Optional[Log]:
        """
        Record an audit log entry.
        Automatically captures HTTP context when invoked inside a Flask request.
        Guaranteed to be fail-safe: never raises an uncaught exception to caller.
        """
        try:
            # Auto-populate HTTP context if available
            if has_request_context():
                if method is None:
                    method = request.method
                if endpoint is None:
                    endpoint = request.path
                if ip_address is None:
                    ip_address = get_remote_address()
                if user_agent is None:
                    user_agent = request.headers.get("User-Agent")
                if user_id is None:
                    user_id = session.get("user_id")
                    if user_id is None and hasattr(g, "_current_user") and g._current_user:
                        user_id = getattr(g._current_user, "id", None)

                # Auto-capture request data if not provided and request is JSON
                if request_data is None and request.is_json:
                    request_data = request.get_json(silent=True)

            # Normalize severity
            severity_norm = str(severity).upper().strip()
            if severity_norm not in ("INFO", "WARNING", "ERROR"):
                severity_norm = "INFO"

            # Debounce rapid duplicate rate limit logs
            if action == "RATE_LIMIT" and not skip_rate_limit_debounce:
                now_ts = time.time()
                debounce_key = f"{ip_address}:{user_id}:{endpoint}"
                last_ts = _recent_rate_limits.get(debounce_key, 0)
                if now_ts - last_ts < 5.0:
                    # Skip duplicate rate-limit log within 5 seconds window
                    return None
                _recent_rate_limits[debounce_key] = now_ts

            # Serialize data payloads (redacting passwords & credentials)
            req_str = serialize_payload(request_data)
            res_str = serialize_payload(response_data)

            # Persist to database
            log_entry = Log(
                user_id=user_id,
                action=action.strip().upper(),
                module=module.strip().upper(),
                severity=severity_norm,
                method=method.upper().strip() if method else None,
                endpoint=endpoint.strip() if endpoint else None,
                status_code=status_code,
                ip_address=ip_address.strip() if ip_address else None,
                user_agent=user_agent.strip() if user_agent else None,
                request_data=req_str,
                response_data=res_str,
                description=description.strip() if description else None,
                created_at=datetime.now(timezone.utc),
            )

            db.session.add(log_entry)
            db.session.commit()
            return log_entry

        except Exception as e:
            # Logging failures must NEVER interrupt business operations
            logger.error(f"Audit log recording failed: {e}", exc_info=True)
            try:
                db.session.rollback()
            except Exception:
                pass
            return None

    @staticmethod
    def get_logs(
        page: int = 1,
        per_page: int = 20,
        query: Optional[str] = None,
        severity: Optional[str] = None,
        action: Optional[str] = None,
        module: Optional[str] = None,
        method: Optional[str] = None,
        status_code: Optional[Any] = None,
        user_id: Optional[int] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> Tuple[List[Log], int, dict]:
        """
        Query logs with multi-field search, filtering, and server-side pagination.
        """
        stmt = Log.query

        # Search filter (description, action, endpoint, or IP)
        if query and query.strip():
            term = f"%{query.strip()}%"
            stmt = stmt.filter(
                (Log.description.ilike(term))
                | (Log.action.ilike(term))
                | (Log.endpoint.ilike(term))
                | (Log.ip_address.ilike(term))
            )

        # Severity filter
        if severity and severity.strip().upper() != "ALL":
            stmt = stmt.filter(Log.severity == severity.strip().upper())

        # Action filter
        if action and action.strip().upper() != "ALL":
            stmt = stmt.filter(Log.action == action.strip().upper())

        # Module filter
        if module and module.strip().upper() != "ALL":
            stmt = stmt.filter(Log.module == module.strip().upper())

        # Method filter
        if method and method.strip().upper() != "ALL":
            stmt = stmt.filter(Log.method == method.strip().upper())

        # Status code filter
        if status_code is not None and str(status_code).strip() != "" and str(status_code).upper() != "ALL":
            try:
                sc = int(status_code)
                stmt = stmt.filter(Log.status_code == sc)
            except ValueError:
                pass

        # User filter
        if user_id:
            stmt = stmt.filter(Log.user_id == user_id)

        # Date range filter
        if from_date and from_date.strip():
            try:
                dt_from = datetime.strptime(from_date.strip(), "%Y-%m-%d")
                stmt = stmt.filter(Log.created_at >= dt_from)
            except ValueError:
                pass

        if to_date and to_date.strip():
            try:
                # Include full end day (up to 23:59:59)
                dt_to = datetime.strptime(to_date.strip(), "%Y-%m-%d") + timedelta(days=1)
                stmt = stmt.filter(Log.created_at < dt_to)
            except ValueError:
                pass

        # Sort latest first
        stmt = stmt.order_by(Log.created_at.desc(), Log.id.desc())

        # Pagination
        pagination = stmt.paginate(page=page, per_page=per_page, error_out=False)
        
        meta = {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "pages": pagination.pages,
            "has_prev": pagination.has_prev,
            "has_next": pagination.has_next,
            "prev_num": pagination.prev_num,
            "next_num": pagination.next_num,
        }

        return pagination.items, pagination.total, meta

    @staticmethod
    def get_log_by_id(log_id: int) -> Optional[Log]:
        """Fetch single log by ID."""
        return db.session.get(Log, log_id)

    @staticmethod
    def delete_log(log_id: int) -> bool:
        """Delete a specific log entry by ID."""
        log_entry = db.session.get(Log, log_id)
        if not log_entry:
            return False
        try:
            db.session.delete(log_entry)
            db.session.commit()
            return True
        except Exception as e:
            logger.error(f"Error deleting log {log_id}: {e}")
            db.session.rollback()
            return False

    @staticmethod
    def clear_logs(days: Optional[int] = None) -> int:
        """
        Delete old logs. If days is None, clear all logs.
        Otherwise delete logs older than specified number of days.
        """
        try:
            if days is not None and days > 0:
                cutoff = datetime.now(timezone.utc) - timedelta(days=days)
                count = Log.query.filter(Log.created_at < cutoff).delete()
            else:
                count = Log.query.delete()
            db.session.commit()
            return count
        except Exception as e:
            logger.error(f"Error clearing logs: {e}")
            db.session.rollback()
            return 0

    @staticmethod
    def get_stats() -> dict:
        """Get summary statistics for dashboard badges."""
        try:
            total = Log.query.count()
            info_count = Log.query.filter_by(severity="INFO").count()
            warning_count = Log.query.filter_by(severity="WARNING").count()
            error_count = Log.query.filter_by(severity="ERROR").count()
            return {
                "total": total,
                "info": info_count,
                "warning": warning_count,
                "error": error_count,
            }
        except Exception:
            return {"total": 0, "info": 0, "warning": 0, "error": 0}
