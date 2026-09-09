import json
import io
import unittest
from unittest.mock import patch
from app import app
from extensions import db, limiter
from api.models.user import User
from api.models.log import Log
from api.services.log_service import LogService, redact_sensitive_data, serialize_payload


class LogManagementTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False

    def setUp(self):
        self.app_context = app.app_context()
        self.app_context.push()
        db.create_all()
        limiter.reset()

        # Clean existing test data
        Log.query.delete()
        User.query.filter(User.email.in_([
            "admin_test@test.com",
            "staff_test@test.com",
            "created_user@test.com",
            "updated_user@test.com"
        ])).delete()
        db.session.commit()

        # Create Admin User
        self.admin = User(name="Test Admin", email="admin_test@test.com", role="admin")
        self.admin.set_password("AdminPass123!")
        db.session.add(self.admin)

        # Create Staff User (Non-Admin)
        self.staff = User(name="Test Staff", email="staff_test@test.com", role="staff")
        self.staff.set_password("StaffPass123!")
        db.session.add(self.staff)

        db.session.commit()
        self.client = app.test_client()

    def tearDown(self):
        Log.query.delete()
        User.query.filter(User.email.in_([
            "admin_test@test.com",
            "staff_test@test.com",
            "created_user@test.com",
            "updated_user@test.com"
        ])).delete()
        db.session.commit()
        db.session.remove()
        self.app_context.pop()

    def login_as(self, email, password):
        """Helper to log in a user and set up session."""
        return self.client.post("/login", data={
            "identifier": email,
            "password": password
        }, follow_redirects=True)

    # 1. Login Success creates log
    def test_login_success_creates_log(self):
        res = self.login_as("admin_test@test.com", "AdminPass123!")
        self.assertEqual(res.status_code, 200)

        log = Log.query.filter_by(action="LOGIN", severity="INFO").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.module, "AUTH")
        self.assertEqual(log.user_id, self.admin.id)
        self.assertIn("admin_test@test.com", log.description)
        # Ensure password is not stored anywhere
        self.assertNotIn("AdminPass123!", str(log.request_data))
        self.assertNotIn("AdminPass123!", str(log.description))

    # 2. Login Failure creates warning log without password
    def test_login_failure_creates_warning_log(self):
        res = self.client.post("/login", data={
            "identifier": "admin_test@test.com",
            "password": "WrongPassword999!"
        })
        self.assertEqual(res.status_code, 401)

        log = Log.query.filter_by(action="LOGIN", severity="WARNING").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.module, "AUTH")
        self.assertEqual(log.status_code, 401)
        self.assertIn("Failed login attempt", log.description)
        self.assertNotIn("WrongPassword999!", str(log.request_data))
        self.assertNotIn("WrongPassword999!", str(log.description))

    # 3. Logout creates log
    def test_logout_creates_log(self):
        self.login_as("admin_test@test.com", "AdminPass123!")
        res = self.client.get("/logout", follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        log = Log.query.filter_by(action="LOGOUT").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.severity, "INFO")
        self.assertEqual(log.module, "AUTH")
        self.assertEqual(log.user_id, self.admin.id)
        self.assertIn("logged out", log.description)

    # 4. User CRUD creates logs
    def test_user_crud_creates_logs(self):
        self.login_as("admin_test@test.com", "AdminPass123!")

        # CREATE USER
        create_res = self.client.post("/admin/users", json={
            "name": "Created User",
            "email": "created_user@test.com",
            "role": "staff",
            "password": "SecretPassword123!"
        })
        self.assertEqual(create_res.status_code, 201)
        new_user_data = create_res.get_json()
        new_user_id = new_user_data["id"]

        create_log = Log.query.filter_by(action="CREATE_USER").first()
        self.assertIsNotNone(create_log)
        self.assertEqual(create_log.severity, "INFO")
        self.assertEqual(create_log.module, "USERS")
        self.assertIn("Created user Created User", create_log.description)
        # Password must not be in request or response data
        self.assertNotIn("SecretPassword123!", str(create_log.request_data))
        self.assertNotIn("SecretPassword123!", str(create_log.response_data))

        # UPDATE USER
        update_res = self.client.put(f"/admin/users/{new_user_id}", json={
            "name": "Updated User",
            "email": "updated_user@test.com",
            "role": "manager"
        })
        self.assertEqual(update_res.status_code, 200)

        update_log = Log.query.filter_by(action="UPDATE_USER").first()
        self.assertIsNotNone(update_log)
        self.assertEqual(update_log.severity, "INFO")
        self.assertIn("Updated user Updated User", update_log.description)

        # DELETE USER
        del_res = self.client.delete(f"/admin/users/{new_user_id}")
        self.assertEqual(del_res.status_code, 200)

        del_log = Log.query.filter_by(action="DELETE_USER").first()
        self.assertIsNotNone(del_log)
        self.assertEqual(del_log.severity, "INFO")
        self.assertIn(f"Deleted user Updated User", del_log.description)

    # 5. Image upload and removal creates logs
    def test_image_upload_and_removal_creates_logs(self):
        from PIL import Image
        self.login_as("admin_test@test.com", "AdminPass123!")

        img = Image.new("RGB", (100, 100), color="blue")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)

        # Create user with profile image
        res = self.client.post("/admin/users", data={
            "name": "Image User",
            "email": "created_user@test.com",
            "role": "staff",
            "password": "Password123!",
            "profile": (buf, "test_avatar.jpg", "image/jpeg"),
        }, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 201)
        created_id = res.get_json()["id"]

        upload_log = Log.query.filter_by(action="UPLOAD_IMAGE").first()
        self.assertIsNotNone(upload_log)
        self.assertEqual(upload_log.severity, "INFO")
        self.assertIn("Uploaded profile image", upload_log.description)

        # Remove image
        res_remove = self.client.post(f"/admin/users/{created_id}", data={
            "name": "Image User",
            "email": "created_user@test.com",
            "role": "staff",
            "remove_profile": "true",
        })
        self.assertEqual(res_remove.status_code, 200)

        remove_log = Log.query.filter_by(action="REMOVE_IMAGE").first()
        self.assertIsNotNone(remove_log)
        self.assertEqual(remove_log.severity, "INFO")
        self.assertIn("Removed profile image", remove_log.description)

    # 6. Rate Limit violations create warning logs
    def test_rate_limit_violation_creates_warning_log(self):
        # Trigger rate limit on login endpoint (limit: 5 per minute)
        for _ in range(6):
            self.client.post("/login", data={
                "identifier": "nonexistent@test.com",
                "password": "wrong"
            })

        rate_log = Log.query.filter_by(action="RATE_LIMIT").first()
        self.assertIsNotNone(rate_log)
        self.assertEqual(rate_log.severity, "WARNING")
        self.assertEqual(rate_log.status_code, 429)
        self.assertEqual(rate_log.module, "RATE_LIMIT")

    # 7. Redaction of sensitive fields
    def test_sensitive_data_redaction(self):
        payload = {
            "name": "John Doe",
            "password": "SuperSecretPassword!",
            "confirm_password": "SuperSecretPassword!",
            "token": "bearer_xyz_12345",
            "nested": {
                "auth": "secret_key",
                "normal": "visible_value"
            }
        }
        sanitized = redact_sensitive_data(payload)
        self.assertEqual(sanitized["name"], "John Doe")
        self.assertEqual(sanitized["password"], "[REDACTED]")
        self.assertEqual(sanitized["confirm_password"], "[REDACTED]")
        self.assertEqual(sanitized["token"], "[REDACTED]")
        self.assertEqual(sanitized["nested"]["auth"], "[REDACTED]")
        self.assertEqual(sanitized["nested"]["normal"], "visible_value")

    # 8. request_data and response_data remain NULL when unavailable
    def test_null_payloads_when_unavailable(self):
        self.assertIsNone(serialize_payload(None))
        self.assertIsNone(serialize_payload({}))
        self.assertIsNone(serialize_payload([]))

        # Direct log without payloads
        entry = LogService.log(
            action="TEST_NULL",
            module="TEST",
            severity="INFO",
            request_data=None,
            response_data=None
        )
        self.assertIsNotNone(entry)
        self.assertIsNone(entry.request_data)
        self.assertIsNone(entry.response_data)

    # 9. Non-admin users cannot access /admin/logs (403 Forbidden)
    def test_non_admin_cannot_access_logs(self):
        # 1. Unauthenticated -> redirects to login
        res = self.client.get("/admin/logs")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers["Location"])

        # 2. Staff (non-admin) browser request -> 403 Forbidden
        self.login_as("staff_test@test.com", "StaffPass123!")
        res = self.client.get("/admin/logs")
        self.assertEqual(res.status_code, 403)

        # 3. Staff AJAX request -> 403 JSON
        res_ajax = self.client.get("/admin/logs", headers={"X-Requested-With": "XMLHttpRequest"})
        self.assertEqual(res_ajax.status_code, 403)
        self.assertEqual(res_ajax.get_json()["error"], "Forbidden")

    # 10. Admin can access, filter, search, and paginate logs
    def test_admin_log_queries_and_pagination(self):
        self.login_as("admin_test@test.com", "AdminPass123!")

        # Create multiple dummy log entries
        for i in range(25):
            LogService.log(
                action=f"ACTION_{i}",
                module="USERS" if i % 2 == 0 else "AUTH",
                severity="INFO" if i < 20 else "ERROR",
                description=f"Log item description number {i}",
                status_code=200 if i < 20 else 500,
                endpoint=f"/admin/endpoint/{i}"
            )

        # Access page 1 via HTML
        res = self.client.get("/admin/logs?page=1&per_page=10")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Audit Logs", res.data)

        # Access via JSON / AJAX
        res_json = self.client.get("/admin/logs?page=1&per_page=10&format=json")
        self.assertEqual(res_json.status_code, 200)
        data = res_json.get_json()
        self.assertEqual(len(data["logs"]), 10)
        self.assertEqual(data["meta"]["pages"], 3)
        self.assertEqual(data["meta"]["page"], 1)

        # Filter by severity=ERROR
        res_error = self.client.get("/admin/logs?severity=ERROR&format=json")
        err_data = res_error.get_json()
        self.assertTrue(all(l["severity"] == "ERROR" for l in err_data["logs"]))

        # Search query
        res_search = self.client.get("/admin/logs?q=number 5&format=json")
        search_data = res_search.get_json()
        self.assertEqual(len(search_data["logs"]), 1)
        self.assertIn("number 5", search_data["logs"][0]["description"])

    # 11. Admin view single log detail
    def test_get_log_detail(self):
        self.login_as("admin_test@test.com", "AdminPass123!")
        entry = LogService.log(
            action="INSPECT_TEST",
            module="SYSTEM",
            severity="INFO",
            request_data={"hello": "world"},
            response_data={"status": "ok"}
        )

        res = self.client.get(f"/admin/logs/{entry.id}")
        self.assertEqual(res.status_code, 200)
        detail = res.get_json()
        self.assertEqual(detail["id"], entry.id)
        self.assertEqual(detail["action"], "INSPECT_TEST")
        self.assertIn("world", detail["request_data"])

    # 12. Delete single log
    def test_delete_single_log(self):
        self.login_as("admin_test@test.com", "AdminPass123!")
        entry = LogService.log(
            action="DELETE_TARGET",
            module="SYSTEM",
            severity="INFO"
        )
        log_id = entry.id

        del_res = self.client.delete(f"/admin/logs/{log_id}")
        self.assertEqual(del_res.status_code, 200)
        self.assertIsNone(db.session.get(Log, log_id))

    # 13. Bulk clear logs
    def test_clear_logs(self):
        self.login_as("admin_test@test.com", "AdminPass123!")
        LogService.log(action="TO_BE_CLEARED_1", module="SYSTEM")
        LogService.log(action="TO_BE_CLEARED_2", module="SYSTEM")

        clear_res = self.client.post("/admin/logs/clear", json={"days": "all"})
        self.assertEqual(clear_res.status_code, 200)
        # Note: clearing logs will log one "DELETE_LOGS" action
        remaining = Log.query.filter(Log.action.in_(["TO_BE_CLEARED_1", "TO_BE_CLEARED_2"])).count()
        self.assertEqual(remaining, 0)

    # 14. Fail-safe: logging error never crashes business flow
    def test_failsafe_logging(self):
        with patch("api.services.log_service.db.session.add", side_effect=Exception("Database down!")):
            result = LogService.log(action="FAILSAFE", module="SYSTEM")
            self.assertIsNone(result)  # Must return None without raising exception


if __name__ == "__main__":
    unittest.main()
