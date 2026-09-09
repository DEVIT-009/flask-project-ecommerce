from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    profile = db.Column(db.String(255), nullable=True)   # profile image path
    email = db.Column(db.String(120), nullable=False, unique=True)
    role = db.Column(db.String(50), nullable=False, default="staff")
    password = db.Column(db.String(255), nullable=False)

    def set_password(self, plain_password: str) -> None:
        """Hash and store a new password."""
        self.password = generate_password_hash(plain_password)

    def check_password(self, plain_password: str) -> bool:
        """Verify the password against the stored hash or legacy plaintext."""
        if not self.password or not plain_password:
            return False
        # Standard werkzeug hash verification
        try:
            if check_password_hash(self.password, plain_password):
                return True
        except ValueError:
            pass
        # Fallback for legacy plaintext password (will be upgraded upon successful login)
        if self.password == plain_password:
            return True
        return False

    @property
    def is_active(self) -> bool:
        """Check if user account is active."""
        status = getattr(self, "status", None)
        if status is not None:
            return str(status).lower() in ("active", "true", "1")
        return True

    @property
    def initials(self) -> str:
        """Return 2 uppercase initials for avatar placeholder."""
        if not self.name:
            return "U"
        parts = self.name.strip().split()
        if len(parts) >= 2:
            return f"{parts[0][0]}{parts[1][0]}".upper()
        return self.name[:2].upper()

    @property
    def profile_thumb(self) -> str | None:
        """Return thumbnail image filename (thm_{uuid}.{ext}) or None."""
        if not self.profile:
            return None
        if self.profile.startswith("thm_") or self.profile.startswith("org_"):
            return self.profile
        return f"thm_{self.profile}"

    @property
    def profile_org(self) -> str | None:
        """Return original image filename (org_{uuid}.{ext}) or None."""
        if not self.profile:
            return None
        if self.profile.startswith("thm_") or self.profile.startswith("org_"):
            return self.profile
        return f"org_{self.profile}"

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "profile": self.profile,
            "profile_thumb": self.profile_thumb,
            "profile_org": self.profile_org,
            "email": self.email,
            "role": self.role,
        }