import unittest
from app import app
from extensions import db, limiter
from api.models.user import User


class RateLimiterTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        app.config["RATELIMIT_STORAGE_URI"] = "memory://"

    def setUp(self):
        self.app_context = app.app_context()
        self.app_context.push()
        db.create_all()
        limiter.reset()

        self.test_emails = ["limiter_admin1@test.com", "limiter_admin2@test.com"]
        User.query.filter(User.email.in_(self.test_emails)).delete()
        db.session.commit()

        # User 1
        self.user1 = User(
            name="Limiter Admin 1",
            email="limiter_admin1@test.com",
            role="admin",
        )
        self.user1.set_password("AdminPass123!")
        db.session.add(self.user1)

        # User 2
        self.user2 = User(
            name="Limiter Admin 2",
            email="limiter_admin2@test.com",
            role="admin",
        )
        self.user2.set_password("AdminPass123!")
        db.session.add(self.user2)
        db.session.commit()

        self.client = app.test_client()

    def tearDown(self):
        User.query.filter(User.email.in_(self.test_emails)).delete()
        db.session.commit()
        limiter.reset()
        db.session.remove()
        self.app_context.pop()

    def test_login_rate_limit_per_ip(self):
        """Login must permit maximum 5 requests/minute per IP; 6th must return 429."""
        # Make 5 requests to /login
        for i in range(5):
            res = self.client.get("/login")
            self.assertEqual(
                res.status_code, 200,
                f"Expected status 200 on login attempt {i + 1}, got {res.status_code}"
            )

        # 6th request from same IP must be rate limited (429)
        res6 = self.client.get("/login")
        self.assertEqual(res6.status_code, 429)
        self.assertIn(b"Too many request", res6.data)
        self.assertIn(b"429", res6.data)
        self.assertIn(b"Try Again after a minute", res6.data)

    def test_login_post_rate_limit_per_ip(self):
        """POST login attempts must also be rate-limited after 5 requests/minute."""
        for i in range(5):
            res = self.client.post(
                "/login",
                data={"identifier": "wrong@user.com", "password": "wrongpassword"},
            )
            self.assertEqual(res.status_code, 401)

        # 6th attempt hits rate limit
        res6 = self.client.post(
            "/login",
            data={"identifier": "wrong@user.com", "password": "wrongpassword"},
        )
        self.assertEqual(res6.status_code, 429)
        self.assertIn(b"Too many request", res6.data)

    def test_admin_rate_limit_per_authenticated_user(self):
        """Admin dashboard must allow maximum 10 requests/minute per authenticated user ID."""
        # Establish session for User 1
        with self.client.session_transaction() as sess:
            sess["user_id"] = self.user1.id
            sess["user_name"] = self.user1.name
            sess["user_email"] = self.user1.email
            sess["user_role"] = self.user1.role

        # Make 10 requests to /admin/dashboard
        for i in range(10):
            res = self.client.get("/admin/dashboard")
            self.assertEqual(
                res.status_code, 200,
                f"Expected 200 on dashboard request {i + 1}, got {res.status_code}"
            )

        # 11th request must exceed limit and return 429
        res11 = self.client.get("/admin/dashboard")
        self.assertEqual(res11.status_code, 429)
        self.assertIn(b"Too many request", res11.data)
        self.assertIn(b"429", res11.data)

    def test_admin_rate_limit_user_isolation(self):
        """When User 1 is rate limited, User 2 must NOT be blocked (rate limited per user ID)."""
        # User 1 consumes all 10 requests
        client_u1 = app.test_client()
        with client_u1.session_transaction() as sess:
            sess["user_id"] = self.user1.id
            sess["user_name"] = self.user1.name
            sess["user_email"] = self.user1.email
            sess["user_role"] = self.user1.role

        for i in range(10):
            res = client_u1.get("/admin/dashboard")
            self.assertEqual(res.status_code, 200)

        # User 1 is now rate limited
        self.assertEqual(client_u1.get("/admin/dashboard").status_code, 429)

        # User 2 makes a request from the same local IP
        client_u2 = app.test_client()
        with client_u2.session_transaction() as sess:
            sess["user_id"] = self.user2.id
            sess["user_name"] = self.user2.name
            sess["user_email"] = self.user2.email
            sess["user_role"] = self.user2.role

        res_u2 = client_u2.get("/admin/dashboard")
        self.assertEqual(
            res_u2.status_code, 200,
            "User 2 should NOT be rate limited when User 1 exceeds their quota"
        )

    def test_admin_api_ajax_returns_429_json(self):
        """Rate limited AJAX/JSON requests must return HTTP 429 with JSON payload."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = self.user1.id
            sess["user_name"] = self.user1.name
            sess["user_email"] = self.user1.email
            sess["user_role"] = self.user1.role

        # Exhaust 10 requests on /admin/users
        for i in range(10):
            res = self.client.get("/admin/users", headers={"Accept": "application/json"})
            self.assertEqual(res.status_code, 200)

        # 11th request via AJAX/JSON
        res11 = self.client.get(
            "/admin/users",
            headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        self.assertEqual(res11.status_code, 429)
        data = res11.get_json()
        self.assertIsNotNone(data)
        self.assertEqual(data.get("error"), "Too Many Requests")

    def test_direct_429_route(self):
        """Direct access to /429 should render 429 page with status code 429."""
        res = self.client.get("/429")
        self.assertEqual(res.status_code, 429)
        self.assertIn(b"Too many request", res.data)
        self.assertIn(b"429", res.data)
        self.assertIn(b"Try Again after a minute", res.data)

    def test_logout_is_exempt_from_rate_limit(self):
        """Logout route should not be blocked even after multiple requests."""
        for i in range(15):
            res = self.client.get("/logout")
            # Redirects to /login
            self.assertEqual(res.status_code, 302)


if __name__ == "__main__":
    unittest.main()
