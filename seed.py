"""
Database seeder script.
Creates or updates the default Admin user.

Usage:
    python seed.py
    flask seed
"""
from app import app
from extensions import db
from api.models.user import User


def seed_admin(name="Admin", email="admin@bookit.com", password="123", role="admin"):
    """Create or update admin user."""
    with app.app_context():
        admin = User.query.filter(
            (User.name.ilike(name)) | (User.email.ilike(email))
        ).first()

        if admin:
            admin.name = name
            admin.email = email
            admin.role = role
            admin.set_password(password)
            action = "Updated existing"
        else:
            admin = User(
                name=name,
                email=email,
                role=role,
            )
            admin.set_password(password)
            db.session.add(admin)
            action = "Created new"

        db.session.commit()
        print(f"[SUCCESS] {action} user:")
        print(f"  - Name:     {admin.name}")
        print(f"  - Email:    {admin.email}")
        print(f"  - Password: {password}")
        print(f"  - Role:     {admin.role}")
        return admin


if __name__ == "__main__":
    seed_admin()
