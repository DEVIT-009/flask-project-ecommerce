import os
import io
import tempfile
import unittest
from PIL import Image
from werkzeug.datastructures import FileStorage

from app import app
from extensions import db, limiter
from api.models.user import User
from api.util.file_upload import (
    save_profile_image,
    delete_profile_image,
    validate_image_file,
    get_user_img_dir,
    get_thumbnail_filename,
    get_original_filename,
    ALLOWED_EXTENSIONS,
    DEFAULT_PROFILE_IMAGE,
)


def create_test_image_bytes(format="JPEG", size=(200, 100), color="blue"):
    """Helper to generate an in-memory image for testing."""
    mode = "RGBA" if format in ("PNG", "WEBP") else "RGB"
    img = Image.new(mode, size, color=color)
    buf = io.BytesIO()
    img.save(buf, format=format)
    buf.seek(0)
    return buf


class TestFileUpload(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.app.config["WTF_CSRF_ENABLED"] = False

        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        limiter.reset()

        # Clean any leftover test users
        self.test_emails = ["img_admin@test.com", "img_user@test.com", "img_u1@test.com", "img_u2@test.com"]
        User.query.filter(User.email.in_(self.test_emails)).delete()
        db.session.commit()

        self.client = self.app.test_client()
        self.img_dir = get_user_img_dir()
        self.created_files = []

    def tearDown(self):
        # Clean up any test files created on disk
        for fname in self.created_files:
            for prefix in ("org_", "thm_", ""):
                p = os.path.join(self.img_dir, f"{prefix}{fname}")
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
        User.query.filter(User.email.in_(self.test_emails)).delete()
        db.session.commit()
        db.session.remove()
        self.app_context.pop()

    def test_validate_image_file_valid(self):
        """Test validation passes for valid images."""
        buf = create_test_image_bytes(format="JPEG")
        fs = FileStorage(stream=buf, filename="avatar.jpg", content_type="image/jpeg")
        is_valid, err = validate_image_file(fs)
        self.assertTrue(is_valid)
        self.assertIsNone(err)

    def test_validate_image_file_invalid_extension(self):
        """Test validation rejects unsupported extensions."""
        buf = io.BytesIO(b"dummy data")
        fs = FileStorage(stream=buf, filename="document.pdf", content_type="application/pdf")
        is_valid, err = validate_image_file(fs)
        self.assertFalse(is_valid)
        self.assertIn("Invalid image format", err)

    def test_validate_image_file_corrupted(self):
        """Test validation rejects corrupted image content."""
        buf = io.BytesIO(b"not an image at all")
        fs = FileStorage(stream=buf, filename="fake.png", content_type="image/png")
        is_valid, err = validate_image_file(fs)
        self.assertFalse(is_valid)
        self.assertIn("not a valid image", err)

    def test_validate_image_file_empty(self):
        """Test validation rejects empty files."""
        buf = io.BytesIO(b"")
        fs = FileStorage(stream=buf, filename="empty.png", content_type="image/png")
        is_valid, err = validate_image_file(fs)
        self.assertFalse(is_valid)
        self.assertIn("empty", err)

    def test_save_profile_image_creates_two_files_and_resizes_thumbnail(self):
        """
        Verify save_profile_image:
        - Creates org_{uuid}.{ext} with original dimensions (200x100)
        - Creates thm_{uuid}.{ext} with 50% dimensions (100x50)
        - Returns {uuid}.{ext} without org_ or thm_ prefix
        """
        orig_w, orig_h = 200, 100
        buf = create_test_image_bytes(format="JPEG", size=(orig_w, orig_h))
        fs = FileStorage(stream=buf, filename="test_photo.jpg", content_type="image/jpeg")

        raw_filename, err = save_profile_image(fs)
        self.assertIsNone(err)
        self.assertIsNotNone(raw_filename)
        self.created_files.append(raw_filename)

        # Check DB filename format: uuid.hex + .jpg, NO org_ or thm_ prefix
        self.assertFalse(raw_filename.startswith("org_"))
        self.assertFalse(raw_filename.startswith("thm_"))
        self.assertTrue(raw_filename.endswith(".jpg"))

        org_path = os.path.join(self.img_dir, f"org_{raw_filename}")
        thm_path = os.path.join(self.img_dir, f"thm_{raw_filename}")

        # Both files must exist on disk
        self.assertTrue(os.path.exists(org_path), f"Original file {org_path} does not exist.")
        self.assertTrue(os.path.exists(thm_path), f"Thumbnail file {thm_path} does not exist.")

        # Check dimensions
        with Image.open(org_path) as org_img:
            self.assertEqual(org_img.size, (200, 100))

        with Image.open(thm_path) as thm_img:
            self.assertEqual(thm_img.size, (100, 50))

    def test_save_profile_image_png_and_webp(self):
        """Verify PNG and WEBP formats generate 50% thumbnail properly."""
        for fmt, ext in (("PNG", ".png"), ("WEBP", ".webp")):
            buf = create_test_image_bytes(format=fmt, size=(300, 150))
            fs = FileStorage(stream=buf, filename=f"test{ext}", content_type=f"image/{fmt.lower()}")
            raw_filename, err = save_profile_image(fs)
            self.assertIsNone(err)
            self.created_files.append(raw_filename)

            org_path = os.path.join(self.img_dir, f"org_{raw_filename}")
            thm_path = os.path.join(self.img_dir, f"thm_{raw_filename}")

            self.assertTrue(os.path.exists(org_path))
            self.assertTrue(os.path.exists(thm_path))

            with Image.open(org_path) as o:
                self.assertEqual(o.size, (300, 150))
            with Image.open(thm_path) as t:
                self.assertEqual(t.size, (150, 75))

    def test_delete_profile_image_removes_both_files(self):
        """Verify delete_profile_image removes both org_ and thm_ files."""
        buf = create_test_image_bytes(format="JPEG", size=(100, 100))
        fs = FileStorage(stream=buf, filename="del_test.jpg", content_type="image/jpeg")
        raw_filename, _ = save_profile_image(fs)
        self.created_files.append(raw_filename)

        org_path = os.path.join(self.img_dir, f"org_{raw_filename}")
        thm_path = os.path.join(self.img_dir, f"thm_{raw_filename}")
        self.assertTrue(os.path.exists(org_path))
        self.assertTrue(os.path.exists(thm_path))

        # Delete image
        result = delete_profile_image(raw_filename)
        self.assertTrue(result)
        self.assertFalse(os.path.exists(org_path))
        self.assertFalse(os.path.exists(thm_path))

    def test_delete_profile_image_protects_default_and_shared(self):
        """Verify delete_profile_image never deletes default.svg or image referenced by another user."""
        self.assertFalse(delete_profile_image(DEFAULT_PROFILE_IMAGE))
        self.assertFalse(delete_profile_image(""))

        # User references an image
        user = User(name="User 1", email="img_u1@test.com", password="pwd", profile="shared.jpg")
        db.session.add(user)
        db.session.commit()

        # Attempt to delete shared image
        self.assertFalse(delete_profile_image("shared.jpg"))

    def test_user_model_properties_and_dict(self):
        """Verify User model profile_thumb, profile_org, and to_dict()."""
        user = User(name="Alex Smith", email="alex@test.com", password="pwd", profile="abcdef123456.png")
        self.assertEqual(user.profile_thumb, "thm_abcdef123456.png")
        self.assertEqual(user.profile_org, "org_abcdef123456.png")

        user_dict = user.to_dict()
        self.assertEqual(user_dict["profile"], "abcdef123456.png")
        self.assertEqual(user_dict["profile_thumb"], "thm_abcdef123456.png")
        self.assertEqual(user_dict["profile_org"], "org_abcdef123456.png")

        # When profile is None
        user2 = User(name="Bob", email="bob@test.com", password="pwd", profile=None)
        self.assertIsNone(user2.profile_thumb)
        self.assertIsNone(user2.profile_org)

    def test_admin_create_and_delete_user_with_image_flow(self):
        """Test full HTTP API flow: create user with image -> verify 2 files -> delete user -> verify cleanup."""
        # Create admin user for auth
        admin = User(name="Admin", email="img_admin@test.com", role="admin")
        admin.set_password("AdminPass123!")
        db.session.add(admin)
        db.session.commit()

        # Login
        login_res = self.client.post("/login", data={"identifier": "img_admin@test.com", "password": "AdminPass123!"})
        self.assertEqual(login_res.status_code, 302)

        # Create user with profile image
        img_buf = create_test_image_bytes(format="JPEG", size=(250, 120))
        data = {
            "name": "Jane Doe",
            "email": "img_user@test.com",
            "role": "staff",
            "password": "Password123!",
            "profile": (img_buf, "jane_avatar.jpg", "image/jpeg"),
        }
        res = self.client.post("/admin/users", data=data, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 201)
        resp_json = res.get_json()
        saved_filename = resp_json["profile"]
        self.created_files.append(saved_filename)

        # Stored without prefix in DB
        self.assertFalse(saved_filename.startswith("org_"))
        self.assertFalse(saved_filename.startswith("thm_"))

        # Both files exist on disk
        org_path = os.path.join(self.img_dir, f"org_{saved_filename}")
        thm_path = os.path.join(self.img_dir, f"thm_{saved_filename}")
        self.assertTrue(os.path.exists(org_path))
        self.assertTrue(os.path.exists(thm_path))

        with Image.open(org_path) as o:
            self.assertEqual(o.size, (250, 120))
        with Image.open(thm_path) as t:
            self.assertEqual(t.size, (125, 60))

        # Delete the user
        user_id = resp_json["id"]
        del_res = self.client.delete(f"/admin/users/{user_id}")
        self.assertEqual(del_res.status_code, 200)

        # Both files deleted from disk
        self.assertFalse(os.path.exists(org_path))
        self.assertFalse(os.path.exists(thm_path))

    def test_admin_update_user_replaces_image_files(self):
        """Test updating user with new image deletes old org_/thm_ and creates new org_/thm_."""
        # Create admin user for auth
        admin = User(name="Admin", email="img_admin@test.com", role="admin")
        admin.set_password("AdminPass123!")
        db.session.add(admin)
        db.session.commit()

        # Login
        self.client.post("/login", data={"identifier": "img_admin@test.com", "password": "AdminPass123!"})

        # Create user with initial image
        buf1 = create_test_image_bytes(format="JPEG", size=(200, 200), color="green")
        create_res = self.client.post("/admin/users", data={
            "name": "Update User",
            "email": "img_user@test.com",
            "role": "staff",
            "password": "Password123!",
            "profile": (buf1, "initial.jpg", "image/jpeg"),
        }, content_type="multipart/form-data")
        self.assertEqual(create_res.status_code, 201)
        old_profile = create_res.get_json()["profile"]
        self.created_files.append(old_profile)

        old_org = os.path.join(self.img_dir, f"org_{old_profile}")
        old_thm = os.path.join(self.img_dir, f"thm_{old_profile}")
        self.assertTrue(os.path.exists(old_org))
        self.assertTrue(os.path.exists(old_thm))

        user_id = create_res.get_json()["id"]

        # Update with new image
        buf2 = create_test_image_bytes(format="PNG", size=(160, 80), color="yellow")
        update_res = self.client.post(f"/admin/users/{user_id}", data={
            "name": "Update User",
            "email": "img_user@test.com",
            "role": "staff",
            "profile": (buf2, "new_photo.png", "image/png"),
        }, content_type="multipart/form-data")
        self.assertEqual(update_res.status_code, 200)
        new_profile = update_res.get_json()["profile"]
        self.created_files.append(new_profile)

        self.assertNotEqual(old_profile, new_profile)
        self.assertFalse(new_profile.startswith("org_"))
        self.assertFalse(new_profile.startswith("thm_"))

        # Old files must be deleted
        self.assertFalse(os.path.exists(old_org))
        self.assertFalse(os.path.exists(old_thm))

        # New files must exist with correct dimensions
        new_org = os.path.join(self.img_dir, f"org_{new_profile}")
        new_thm = os.path.join(self.img_dir, f"thm_{new_profile}")
        self.assertTrue(os.path.exists(new_org))
        self.assertTrue(os.path.exists(new_thm))

        with Image.open(new_org) as o:
            self.assertEqual(o.size, (160, 80))
        with Image.open(new_thm) as t:
            self.assertEqual(t.size, (80, 40))

    def test_admin_update_user_removes_profile(self):
        """Test remove_profile flag deletes files and resets DB profile."""
        admin = User(name="Admin", email="img_admin@test.com", role="admin")
        admin.set_password("AdminPass123!")
        db.session.add(admin)
        db.session.commit()

        self.client.post("/login", data={"identifier": "img_admin@test.com", "password": "AdminPass123!"})

        buf = create_test_image_bytes(format="JPEG", size=(100, 100))
        create_res = self.client.post("/admin/users", data={
            "name": "Remove User",
            "email": "img_user@test.com",
            "role": "staff",
            "password": "Password123!",
            "profile": (buf, "avatar.jpg", "image/jpeg"),
        }, content_type="multipart/form-data")
        self.assertEqual(create_res.status_code, 201)
        profile = create_res.get_json()["profile"]
        self.created_files.append(profile)

        org_path = os.path.join(self.img_dir, f"org_{profile}")
        thm_path = os.path.join(self.img_dir, f"thm_{profile}")
        self.assertTrue(os.path.exists(org_path))
        self.assertTrue(os.path.exists(thm_path))

        user_id = create_res.get_json()["id"]

        # Send update with remove_profile=true
        update_res = self.client.post(f"/admin/users/{user_id}", data={
            "name": "Remove User",
            "email": "img_user@test.com",
            "role": "staff",
            "remove_profile": "true",
        }, content_type="multipart/form-data")
        self.assertEqual(update_res.status_code, 200)
        self.assertIsNone(update_res.get_json()["profile"])

        # Files must be cleaned up from disk
        self.assertFalse(os.path.exists(org_path))
        self.assertFalse(os.path.exists(thm_path))

    def test_delete_profile_image_handles_prefixed_or_legacy_names(self):
        """Verify delete_profile_image handles filenames whether passed with or without org_/thm_ prefix."""
        buf = create_test_image_bytes(format="JPEG", size=(100, 100))
        fs = FileStorage(stream=buf, filename="prefix_test.jpg", content_type="image/jpeg")
        raw_name, _ = save_profile_image(fs)
        self.created_files.append(raw_name)

        # Call delete with 'org_' prefix - should still delete both
        result = delete_profile_image(f"org_{raw_name}")
        self.assertTrue(result)
        self.assertFalse(os.path.exists(os.path.join(self.img_dir, f"org_{raw_name}")))
        self.assertFalse(os.path.exists(os.path.join(self.img_dir, f"thm_{raw_name}")))


if __name__ == "__main__":
    unittest.main()
