import unittest
from app import app
from extensions import db, limiter
from api.models.user import User
from werkzeug.security import check_password_hash


class AuthTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False

    def setUp(self):
        self.app_context = app.app_context()
        self.app_context.push()
        db.create_all()
        limiter.reset()

        # Clean any leftover test users
        User.query.filter(User.email.in_(["admin@test.com", "legacy@test.com", "alice@test.com", "alice_up@test.com", "new@test.com"])).delete()
        db.session.commit()

        # Create test hashed user
        u1 = User(
            name="Admin Tester",
            email="admin@test.com",
            role="admin",
        )
        u1.set_password("SecurePass123!")
        db.session.add(u1)

        # Create test user with legacy plaintext password
        u2 = User(
            name="Legacy User",
            email="legacy@test.com",
            role="staff",
            password="PlainPassword123",
        )
        db.session.add(u2)
        db.session.commit()

        self.client = app.test_client()

    def tearDown(self):
        User.query.filter(User.email.in_(["admin@test.com", "legacy@test.com", "alice@test.com", "alice_up@test.com", "new@test.com"])).delete()
        db.session.commit()
        db.session.remove()
        self.app_context.pop()

    def test_unauthenticated_redirect(self):
        """Unauthenticated requests to admin dashboard should redirect to login."""
        response = self.client.get("/admin/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])
        self.assertIn("next=/admin/dashboard", response.headers["Location"])

    def test_unauthenticated_ajax_unauthorized(self):
        """Unauthenticated AJAX requests to protected routes should receive 401 JSON."""
        response = self.client.post(
            "/admin/users",
            json={"name": "New User", "email": "new@test.com", "password": "pass"},
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)

    def test_login_page_renders(self):
        """Login page should render 200 OK with login form."""
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Bookit Admin", response.data)
        self.assertIn(b"identifier", response.data)
        self.assertIn(b"password", response.data)

    def test_login_invalid_credentials(self):
        """Invalid credentials should return 401 and generic error."""
        response = self.client.post(
            "/login",
            data={"identifier": "admin@test.com", "password": "WrongPassword!"},
            follow_redirects=True
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn(b"Invalid email/username or password", response.data)

    def test_login_nonexistent_user(self):
        """Non-existent username should return 401 with identical generic error."""
        response = self.client.post(
            "/login",
            data={"identifier": "nonexistent@test.com", "password": "AnyPassword"},
            follow_redirects=True
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn(b"Invalid email/username or password", response.data)

    def test_login_successful(self):
        """Valid login should establish session and redirect to dashboard."""
        response = self.client.post(
            "/login",
            data={"identifier": "admin@test.com", "password": "SecurePass123!"},
            follow_redirects=False
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/admin/dashboard")

        with self.client.session_transaction() as sess:
            self.assertIn("user_id", sess)
            self.assertEqual(sess["user_email"], "admin@test.com")

        # Now dashboard should be accessible
        dash_response = self.client.get("/admin/dashboard")
        self.assertEqual(dash_response.status_code, 200)
        self.assertIn(b"Admin Tester", dash_response.data)

    def test_login_with_next_redirect(self):
        """Login with next param should safely redirect to intended destination."""
        response = self.client.post(
            "/login?next=/admin/users",
            data={"identifier": "admin@test.com", "password": "SecurePass123!", "next": "/admin/users"},
            follow_redirects=False
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/admin/users")

    def test_login_open_redirect_protection(self):
        """Unsafe next parameter must be rejected and defaulted to dashboard."""
        response = self.client.post(
            "/login",
            data={"identifier": "admin@test.com", "password": "SecurePass123!", "next": "https://evil.com"},
            follow_redirects=False
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/admin/dashboard")

    def test_legacy_plaintext_password_upgrade(self):
        """Logging in with a legacy plaintext password should succeed and upgrade hash in DB."""
        response = self.client.post(
            "/login",
            data={"identifier": "legacy@test.com", "password": "PlainPassword123"},
            follow_redirects=False
        )
        self.assertEqual(response.status_code, 302)

        # Verify password in DB is now hashed
        with app.app_context():
            u = User.query.filter_by(email="legacy@test.com").first()
            self.assertNotEqual(u.password, "PlainPassword123")
            self.assertTrue(check_password_hash(u.password, "PlainPassword123"))

    def test_user_crud_flow_authenticated(self):
        """User CRUD should work seamlessly when authenticated."""
        # 1. Login
        self.client.post(
            "/login",
            data={"identifier": "admin@test.com", "password": "SecurePass123!"},
        )

        # 2. View user list
        list_res = self.client.get("/admin/users")
        self.assertEqual(list_res.status_code, 200)

        # 3. Create user
        create_res = self.client.post(
            "/admin/users",
            data={"name": "Alice Wonderland", "email": "alice@test.com", "role": "staff", "password": "Password123!"}
        )
        self.assertEqual(create_res.status_code, 201)
        user_id = create_res.get_json()["id"]

        # 4. Fetch single user
        get_res = self.client.get(f"/admin/users/{user_id}")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.get_json()["name"], "Alice Wonderland")

        # 5. Update user
        update_res = self.client.post(
            f"/admin/users/{user_id}",
            data={"name": "Alice Updated", "email": "alice_up@test.com", "role": "admin"}
        )
        self.assertEqual(update_res.status_code, 200)
        self.assertEqual(update_res.get_json()["name"], "Alice Updated")

        # 6. Delete user
        del_res = self.client.delete(f"/admin/users/{user_id}")
        self.assertEqual(del_res.status_code, 200)

    def test_logout_invalidates_session(self):
        """Logout should clear session and redirect back to login."""
        # Login first
        self.client.post(
            "/login",
            data={"identifier": "admin@test.com", "password": "SecurePass123!"},
        )

        # Verify logged in
        dash_res = self.client.get("/admin/dashboard")
        self.assertEqual(dash_res.status_code, 200)

        # Logout
        logout_res = self.client.get("/logout", follow_redirects=False)
        self.assertEqual(logout_res.status_code, 302)
        self.assertEqual(logout_res.headers["Location"], "/login")

        # Verify session cleared
        with self.client.session_transaction() as sess:
            self.assertNotIn("user_id", sess)

        # Accessing dashboard again must redirect to login
        subsequent_res = self.client.get("/admin/dashboard")
        self.assertEqual(subsequent_res.status_code, 302)
        self.assertIn("/login", subsequent_res.headers["Location"])


if __name__ == "__main__":
    unittest.main()
