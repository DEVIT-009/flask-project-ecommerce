# Walkthrough: Enhanced Image Upload Flow (Dual-Image Generation)

We have enhanced the user image upload system to automatically produce both an **original image** and a **50% resized thumbnail** while maintaining existing file storage locations, database schema conventions, error handling/cleanup, and UI display flows.

---

## 1. Image Creation Architecture & Flow

```
[ User Uploads Image ] (FileStorage: JPG, PNG, WEBP, GIF <= 5MB)
                 │
                 ▼
      [ validate_image_file ]
   ├─ 1. Extension validation (Allowed: jpg, jpeg, png, webp, gif)
   ├─ 2. File size verification (Stream seek check <= 5MB)
   └─ 3. Content integrity verification via Pillow (Image.verify)
                 │
           (Valid Image)
                 ▼
      [ save_profile_image ]
   ├─ 1. Generate unique identifier: uuid.uuid4().hex
   ├─ 2. Derive file extension: .{ext}
   │
   ├─ 3. Target File 1: Original Image
   │     - Path: static/assets/user-img/org_{uuid}.{ext}
   │     - Action: Preserves exact original dimensions & metadata
   │
   ├─ 4. Target File 2: Thumbnail Image
   │     - Path: static/assets/user-img/thm_{uuid}.{ext}
   │     - Action: Resized to 50% dimensions (round(w * 0.5), round(h * 0.5))
   │     - Filter: High-quality Lanczos resampling (Image.Resampling.LANCZOS)
   │     - Format-aware handling (RGBA to RGB conversion for JPEG, alpha preservation for PNG/WEBP)
   │
   └─ 5. Return Stored Filename
         - Value: `{uuid}.{ext}` (WITHOUT `org_` or `thm_` prefix)
                 │
                 ▼
      [ Database Persistence ]
   - User.profile column stores: `{uuid}.{ext}`
                 │
         ┌───────┴───────┐
   (Commit Success)   (Commit Fails / Rollback)
         │                       │
         ▼                       ▼
[ Post-Commit Cleanup ]  [ delete_profile_image ]
- Old images deleted      - Newly created `org_` and `thm_`
                          files purged immediately
```

---

## 2. File & Database Naming Rules

| Asset | Location / Field | Naming Pattern | Example |
|---|---|---|---|
| **Database Record** | `User.profile` | `{uuid4().hex}.{ext}` | `c3f81e80a0a54dd6b8b211dc821cf36c.jpg` |
| **Original File (Disk)** | `static/assets/user-img/` | `org_{uuid4().hex}.{ext}` | `org_c3f81e80a0a54dd6b8b211dc821cf36c.jpg` |
| **Thumbnail File (Disk)** | `static/assets/user-img/` | `thm_{uuid4().hex}.{ext}` | `thm_c3f81e80a0a54dd6b8b211dc821cf36c.jpg` |

> [!NOTE]
> The database stores **only** `{uuid4().hex}.{ext}` without any prefix. This keeps the database decoupled from resolution choices and makes future asset generation migrations transparent.

---

## 3. UI Display & Consumption Flow

To ensure high performance and sharp visual rendering, avatars in tables, navigation topbar, and sidebars consume the generated thumbnail (`thm_`):

1. **Jinja Template Helper Properties (`User` Model):**
   - `user.profile_thumb`: Evaluates to `thm_{uuid}.{ext}` (or falls back cleanly if already prefixed or None).
   - `user.profile_org`: Evaluates to `org_{uuid}.{ext}`.
   - `user.to_dict()`: Serializes `profile`, `profile_thumb`, and `profile_org` for REST/AJAX endpoints.

2. **Jinja Template Integration:**
   - Sidebar (`templates/admin/sections/sidebar.html`): Displays `current_user.profile_thumb` with automatic fallback to `current_user.profile` and `default.svg` on error.
   - Topbar (`templates/admin/sections/topbar.html`): Displays `current_user.profile_thumb` with fallback on error.
   - User Table (`templates/admin/layouts/users.html`): Server-rendered rows use `user.profile_thumb`.

3. **Client-Side Dynamic Rendering (`users.html`):**
   - `getAvatarUrl(profile, variant = 'thm')`: Returns `USER_IMG_BASE_URL + 'thm_' + profile` for dynamic rows and edit modal previews.
   - Seamless two-tier image fallback (`dataset.fallback`) guarantees legacy unprefixed files continue displaying without broken image icons.

---

## 4. Deletion & Cleanup Safeguards

The `delete_profile_image(filename)` utility was updated to handle dual-file cleanup:

1. **Prefix Normalization:** Accepts `{uuid}.{ext}`, `org_{uuid}.{ext}`, or `thm_{uuid}.{ext}` and extracts the clean base filename.
2. **Reference Counting:** Queries the database (`User.profile == base_filename`) to ensure no other user record references the image before deleting.
3. **Protected Files:** Explicitly refuses to delete `default.svg` or empty inputs.
4. **Dual Deletion:** Unlinks both `org_{base_filename}` and `thm_{base_filename}` from disk (as well as legacy unprefixed `{base_filename}` if present).
5. **Rollback Safety:** If user creation or update transaction fails in Flask-SQLAlchemy, `delete_profile_image()` is automatically triggered in the `except` block to prevent orphaned files.

---

## 5. Files Created & Modified

### Modified Files
- [`api/util/file_upload.py`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/api/util/file_upload.py) — Added dual-file generation (`org_` + `thm_`), 50% Pillow Lanczos thumbnail resizing, image stream validation via `Image.verify()`, helper methods (`get_thumbnail_filename`, `get_original_filename`), and dual-file cleanup in `delete_profile_image()`.
- [`api/models/user.py`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/api/models/user.py) — Added `profile_thumb` and `profile_org` model properties; exposed both properties in `to_dict()`.
- [`templates/admin/sections/sidebar.html`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/templates/admin/sections/sidebar.html) — Updated avatar source to `current_user.profile_thumb` with tiered error fallback.
- [`templates/admin/sections/topbar.html`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/templates/admin/sections/topbar.html) — Updated avatar source to `current_user.profile_thumb` with tiered error fallback.
- [`templates/admin/layouts/users.html`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/templates/admin/layouts/users.html) — Updated table avatar to `user.profile_thumb` and updated JavaScript `getAvatarUrl` function to default to thumbnail prefix.

### Created Files
- [`tests/test_file_upload.py`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/tests/test_file_upload.py) — Comprehensive unit & integration test suite covering image validation, dual-file generation, 50% dimension scaling, deletion safeguards, and HTTP API user CRUD image flows.
- [`_impl/Image_Creation_Flow.md`](file:///Users/devit009/Documents/dev/Py_Flask/flask-mvc-api-service/_impl/Image_Creation_Flow.md) — This specification and architecture documentation file.

---

## 6. Verification Results

All unit and integration tests passed successfully:
```bash
.venv/bin/python -m unittest discover tests
```
- **24 tests passed (0 failures, 0 errors)**
- Verified original file size preservation: `(250, 120)` -> `(250, 120)`
- Verified thumbnail 50% dimension reduction: `(250, 120)` -> `(125, 60)`
- Verified database stores clean filename `{uuid}.{ext}`
- Verified dual-file disk cleanup on user deletion & profile replacement
- Verified error handling & rollback safety
