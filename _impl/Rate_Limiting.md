# Walkthrough: Flask-Limiter Rate Limiting

We have implemented rate limiting for the Bookit Flask application using **Flask-Limiter**, enforcing request throttling on authentication endpoints and the administrative control panel/API while integrating a responsive **HTTP 429 Too Many Requests** page styled with Tailwind CSS and FlyonUI.

---

## 1. Rate Limiting Rules & Policies

| Scope | Rate Limit | Key Function | Identification | Target Endpoints | Exceeded Behavior |
|---|---|---|---|---|---|
| **Authentication (Login)** | **5 requests / minute** | `get_remote_address` | Client IP (`127.0.0.1` locally) | `/login`<br>`/admin/login` | Returns **HTTP 429** + renders 429 Page (or 429 JSON for AJAX) |
| **Admin Panel & API** | **10 requests / minute** | `get_user_id_or_ip` | Authenticated `user:<id>` (or IP fallback) | `/admin`<br>`/admin/dashboard`<br>`/admin/users`<br>`/admin/users/<id>` | Returns **HTTP 429** + renders 429 Page (or 429 JSON for AJAX) |
| **Logout** | **Exempt** | N/A | N/A | `/logout`<br>`/admin/logout` | Always permitted (no session lockout) |

---

## 2. Architecture & Request Flow

```
[ Incoming Request ]
          │
          ▼
 [ Endpoint Router ]
          │
  ┌───────┴─────────────────────────────────────────────┐
  │                                                     │
  ▼                                                     ▼
[ /login or /admin/login ]              [ /admin/* Views & APIs ]
  │                                                     │
  ▼                                                     ▼
[ Rate Limit: 5/min per IP ]            [ @login_required ]
(Key: request.remote_addr)                              │
  │                                                     ▼
  │                                     [ Rate Limit: 10/min per User ]
  │                                     (Key: f"user:{session['user_id']}")
  │                                                     │
  └───────────────────────┬─────────────────────────────┘
                          │
            ┌─────────────┴─────────────┐
            ▼                           ▼
    (Within Quota)              (Limit Exceeded)
            │                           │
            ▼                           ▼
    [ View Function ]           [ RateLimitExceeded Exception ]
    - 200 OK / 201 / 302                │
                                        ▼
                            [ @app.errorhandler(429) ]
                                        │
                            ┌───────────┴───────────┐
                            ▼                       ▼
                    (AJAX / JSON Header)    (Browser Navigation)
                            │                       │
                            ▼                       ▼
                    Return JSON (429)       Render `templates/errors/429.html`
                    { "error": "...",       - Ambient glow + FlyonUI theme
                      "message": "...",     - Live 60-second countdown timer
                      "retry_after": 60 }   - Auto-resetting "Try Again" action
```

---

## 3. Key Implementation Details

### A. Key Functions (`api/util/limiter.py`)
- **`get_user_id_or_ip()`**:
  - Inspects `session.get("user_id")` or `g._current_user.id`.
  - If authenticated, returns `user:<id>` ensuring each user account maintains its own isolated request counter.
  - If unauthenticated, falls back cleanly to `get_remote_address()` (IP).

### B. Extension Setup (`extensions.py` & `config.py`)
- Configured with `RATELIMIT_STORAGE_URI = "memory://"` and `RATELIMIT_STRATEGY = "moving-window"`.
- Cleanly initialized via application factory pattern: `limiter.init_app(app)`.

### C. 429 Error Page (`templates/errors/429.html`)
- Built using the **same FlyonUI / Tailwind CSS design system** as `login.html` and `dashboard.html`.
- **Simplified Minimalist Design:**
  - Ambient glowing backdrop (`bg-warning/15` and `bg-primary/10`).
  - Dark/light mode theme toggle synced with `localStorage['admin-theme']` (`vscode` / `valorant`).
  - Prominent **429** status number (bold monospace text in warning amber).
  - Clean heading: **"Too many request"**.
  - Informative guidance: **"Try Again after a minute"**.
  - Responsive "Try Again" reload button with instant retry action.

### D. Dual Response Error Handling (`app.py`)
- Inspects `X-Requested-With` and `Accept` headers.
- REST/AJAX requests receive clean JSON payloads with HTTP 429.
- Standard web requests render the visual 429 template.
- Registered `/429` route for direct preview and inspection.

---

## 4. Files Created & Modified

### Modified Files
- [`requirements.txt`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/requirements.txt) — Added `flask-limiter==4.1.1` and its dependencies (`limits`, `ordered-set`, `deprecated`).
- [`config.py`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/config.py) — Added `RATELIMIT_STORAGE_URI`, `RATELIMIT_STRATEGY`, and `RATELIMIT_ENABLED`.
- [`extensions.py`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/extensions.py) — Instantiated `Limiter(key_func=get_remote_address, storage_uri="memory://", strategy="moving-window")`.
- [`app.py`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/app.py) — Initialized `limiter.init_app(app)`, registered 429 error handler, and added `/429` direct preview route.
- [`admin/route.py`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/admin/route.py) — Applied `5 per minute` on `/login` & `/admin/login`, `10 per minute` per user ID on admin views and user management APIs, and exempted `/logout`.
- [`tests/test_auth.py`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/tests/test_auth.py) — Added `limiter.reset()` in test setup.
- [`tests/test_file_upload.py`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/tests/test_file_upload.py) — Added `limiter.reset()` in test setup.

### Created Files
- [`api/util/limiter.py`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/api/util/limiter.py) — Defined `get_user_id_or_ip()` and `get_client_ip()` key functions.
- [`templates/errors/429.html`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/templates/errors/429.html) — 429 Too Many Requests template with FlyonUI styling, ambient lighting, theme toggle, and live timer.
- [`tests/test_rate_limiter.py`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/tests/test_rate_limiter.py) — Comprehensive automated tests for IP limits, user ID limits, user quota isolation, AJAX JSON responses, and logout exemption.
- [`_impl/Rate_Limiting.md`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/_impl/Rate_Limiting.md) — Documentation specification for rate limiting rules.

---

## 5. Verification Results

All automated tests passed:
```bash
.venv/bin/python -m unittest discover tests
```
- **31 total tests ran and passed (0 errors, 0 failures)**
  - `test_login_rate_limit_per_ip`: Passed (5 requests allowed, 6th returns 429).
  - `test_login_post_rate_limit_per_ip`: Passed (POST brute-force blocked on 6th request).
  - `test_admin_rate_limit_per_authenticated_user`: Passed (10 requests allowed, 11th returns 429).
  - `test_admin_rate_limit_user_isolation`: Passed (User 2 remains unblocked when User 1 exhausts limit).
  - `test_admin_api_ajax_returns_429_json`: Passed (AJAX requests receive 429 JSON).
  - `test_direct_429_route`: Passed (Returns 429 and renders FlyonUI page).
  - `test_logout_is_exempt_from_rate_limit`: Passed (Multiple logouts permitted).
