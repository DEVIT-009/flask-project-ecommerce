from datetime import datetime, timezone
import json
from extensions import db


class Log(db.Model):
    __tablename__ = "logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = db.Column(db.String(50), nullable=False)
    module = db.Column(db.String(50), nullable=False)
    severity = db.Column(db.String(20), nullable=False, default="INFO")
    method = db.Column(db.String(10), nullable=True)
    endpoint = db.Column(db.String(255), nullable=True)
    status_code = db.Column(db.Integer, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)
    request_data = db.Column(db.Text, nullable=True)
    response_data = db.Column(db.Text, nullable=True)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", backref=db.backref("logs", lazy=True))

    @property
    def request_json(self):
        """Return parsed request_data dictionary if valid JSON, else None."""
        if not self.request_data:
            return None
        try:
            return json.loads(self.request_data)
        except (ValueError, TypeError):
            return self.request_data

    @property
    def response_json(self):
        """Return parsed response_data dictionary if valid JSON, else None."""
        if not self.response_data:
            return None
        try:
            return json.loads(self.response_data)
        except (ValueError, TypeError):
            return self.response_data

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "user_name": self.user.name if self.user else "System",
            "user_email": self.user.email if self.user else None,
            "action": self.action,
            "module": self.module,
            "severity": self.severity,
            "method": self.method,
            "endpoint": self.endpoint,
            "status_code": self.status_code,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "request_data": self.request_data,
            "response_data": self.response_data,
            "description": self.description,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }
