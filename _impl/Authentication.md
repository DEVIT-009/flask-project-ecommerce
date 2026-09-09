# Walkthrough: Session-Based Authentication

We have implemented a session-based authentication system for the Bookit Admin dashboard while maintaining the existing MVC architecture and Tailwind + FlyonUI design system.

---

## 1. Authentication Flow

```
[ User accesses /admin or /admin/dashboard ]
                    │
           (No active session)
                    ▼
          Redirect to /login?next=/admin/...
                    │
            [ Login Form View ]
   (Email / Username + Password + Remember Me)
                    │
          (POST to /login)
                    │
                    ▼
          [ AuthService.authenticate ]
     ├─ 1. Query user by identifier (email / name)
     ├─ 2. Secure password hash verification (werkzeug)
     ├─ 3. Timing-attack mitigation
     ├─ 4. Account status / active validation
     └─ 5. Transparent legacy password upgrade
                    │
          (Valid Credentials)
                    ▼
          [ AuthService.login_user ]
     ├─ Clear old session (fixation defense)
     ├─ Store user_id, name, email, role, login_time
     └─ Set session permanence & cookie security
                    │
                    ▼
          Redirect to `next` URL (safe relative paths only)
                    │
                    ▼
          [ Admin Dashboard Access ]
     ├─ Topbar & Sidebar display dynamic user data & avatar
     ├─ User CRUD remains fully functional
     └─ Logout clears session & redirects to /login
```

---

## 2. Files Created & Modified

### Created Files
- [`api/repositories/user_repository.py`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/api/repositories/user_repository.py) — Database abstraction for querying and persisting `User` records by ID, email, or username.
- [`api/services/auth_service.py`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/api/services/auth_service.py) — Core authentication logic: credential validation, session fixation protection, session creation, logout, and current user retrieval.
- [`api/util/auth.py`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/api/util/auth.py) — `@login_required` route decorator (handles both HTML redirect and 401 JSON for AJAX/API requests), `load_current_user` before-request hook, and Jinja context processor.
- [`templates/admin/auth/login.html`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/templates/admin/auth/login.html) — Modern, responsive login page built with FlyonUI and Tailwind CSS (featuring password toggle, theme toggle, flash notifications, and Bookit branding).
- [`tests/test_auth.py`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/tests/test_auth.py) — Comprehensive automated test suite (11 test cases).

### Modified Files
- [`config.py`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/config.py) — Configured `SECRET_KEY`, session cookie flags (`SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE`, `SESSION_COOKIE_NAME`), and `PERMANENT_SESSION_LIFETIME`.
- [`app.py`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/app.py) — Initialized `Config`, attached `before_request` and `context_processor` auth hooks.
- [`api/models/user.py`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/api/models/user.py) — Added `set_password()`, `check_password()`, `is_active` property, and `initials` avatar helper.
- [`admin/route.py`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/admin/route.py) — Added `/login`, `/logout`, `/admin` redirect, and applied `@login_required` to all admin routes (`dashboard`, `users`, and user CRUD operations).
- [`templates/admin/sections/topbar.html`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/templates/admin/sections/topbar.html) — Replaced static placeholder user with dynamic `current_user` name, email, avatar/initials, and active logout link.
- [`templates/admin/sections/sidebar.html`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/templates/admin/sections/sidebar.html) — Replaced static footer with dynamic `current_user` info and functional logout button.
- [`templates/web/sections/nav.html`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/templates/web/sections/nav.html) — Updated nav bar "Sign in" / "Dashboard" link to reflect authentication state.

---

## 3. Security Highlights

1. **Password Security**: Passwords are never stored in plain text. Hashing is performed using Werkzeug's secure scrypt/pbkdf2 algorithm. Model `to_dict()` excludes passwords.
2. **Session Fixation Defense**: `session.clear()` is explicitly executed before setting authenticated session keys during login.
3. **Open Redirect Prevention**: `next` query/form parameters are verified to be safe internal relative paths (`startswith('/') and not startswith('//')`) before redirection.
4. **User Enumeration Defense**: Authentication failures consistently report generic errors (`"Invalid email/username or password."`) with dummy hash timing defense.
5. **Cookie Hardening**: `SESSION_COOKIE_HTTPONLY = True`, `SESSION_COOKIE_SAMESITE = 'Lax'`.

---

## 4. Verification & Test Results

All 11 unit and integration tests in `tests/test_auth.py` passed:

```bash
$ .venv/bin/python -m unittest tests/test_auth.py
...........
----------------------------------------------------------------------
Ran 11 tests in 1.363s

OK
```

### Verified Scenarios:
- [x] Unauthenticated request to `/admin/dashboard` redirects to `/login?next=/admin/dashboard`.
- [x] Unauthenticated AJAX/API request returns `401 Unauthorized`.
- [x] Invalid credentials return `401` with generic safe error message.
- [x] Valid login creates session and redirects to destination.
- [x] Authenticated user can access dashboard and all User CRUD features.
- [x] Logout clears session and invalidates access.
- [x] Open redirect parameter attacks are safely prevented.
