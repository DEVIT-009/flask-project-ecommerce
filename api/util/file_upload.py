import os
import uuid
import logging
from flask import current_app
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
DEFAULT_PROFILE_IMAGE = "default.svg"
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


def get_user_img_dir() -> str:
    """Return the absolute path to static/assets/user-img directory."""
    img_dir = os.path.join(current_app.root_path, "static", "assets", "user-img")
    os.makedirs(img_dir, exist_ok=True)
    return img_dir


def allowed_file(filename: str) -> bool:
    """Check if the filename has an allowed image extension."""
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def get_file_extension(filename: str) -> str:
    """Extract lowercase extension including the dot (e.g. .jpg)."""
    if "." in filename:
        return "." + filename.rsplit(".", 1)[1].lower()
    return ""


def validate_image_file(file_storage):
    """
    Validate uploaded file storage object.
    Returns (True, None) if valid, or (False, error_message) if invalid.
    """
    if not file_storage or not file_storage.filename or file_storage.filename.strip() == "":
        return False, "No file selected."

    if not allowed_file(file_storage.filename):
        allowed_list = ", ".join(sorted(ALLOWED_EXTENSIONS))
        return False, f"Invalid image format. Allowed formats: {allowed_list}"

    # Check file size (seek to end and back)
    try:
        file_storage.seek(0, os.SEEK_END)
        size = file_storage.tell()
        file_storage.seek(0)  # Reset pointer for subsequent save
        if size == 0:
            return False, "Uploaded image is empty."
        if size > MAX_FILE_SIZE_BYTES:
            max_mb = MAX_FILE_SIZE_BYTES / (1024 * 1024)
            return False, f"Image size exceeds maximum limit of {max_mb:.0f}MB."
    except Exception as e:
        logger.warning(f"Error checking file size: {e}")

    # Verify image integrity using Pillow
    try:
        file_storage.seek(0)
        with Image.open(file_storage) as img:
            img.verify()
        file_storage.seek(0)
    except Exception as e:
        logger.warning(f"Corrupt or invalid image content: {e}")
        try:
            file_storage.seek(0)
        except Exception:
            pass
        return False, "Uploaded file is not a valid image or is corrupted."

    return True, None


def get_thumbnail_filename(filename: str | None) -> str | None:
    """Return thumbnail filename (thm_{uuid}.{ext}) from a stored profile filename."""
    if not filename or filename == DEFAULT_PROFILE_IMAGE:
        return filename
    if filename.startswith("thm_") or filename.startswith("org_"):
        return filename
    return f"thm_{filename}"


def get_original_filename(filename: str | None) -> str | None:
    """Return original filename (org_{uuid}.{ext}) from a stored profile filename."""
    if not filename or filename == DEFAULT_PROFILE_IMAGE:
        return filename
    if filename.startswith("thm_") or filename.startswith("org_"):
        return filename
    return f"org_{filename}"


def save_profile_image(file_storage):
    """
    Save the uploaded file into static/assets/user-img/ as 2 files:
    1. Original: org_{uuid.uuid4().hex}.{ext} (preserves original dimensions)
    2. Thumbnail: thm_{uuid.uuid4().hex}.{ext} (resized to 50% dimensions)

    The database stores only: {uuid.uuid4().hex}.{ext} (without prefix).
    Returns (raw_filename, None) on success, or (None, error_message) on failure.
    """
    is_valid, error_msg = validate_image_file(file_storage)
    if not is_valid:
        return None, error_msg

    dest_dir = get_user_img_dir()
    ext = get_file_extension(file_storage.filename)
    unique_id = uuid.uuid4().hex
    raw_filename = f"{unique_id}{ext}"
    org_filename = f"org_{raw_filename}"
    thm_filename = f"thm_{raw_filename}"

    org_path = os.path.join(dest_dir, org_filename)
    thm_path = os.path.join(dest_dir, thm_filename)

    try:
        # Save original file preserving exact uploaded content
        file_storage.seek(0)
        file_storage.save(org_path)

        # Generate thumbnail at 50% dimensions using Pillow
        with Image.open(org_path) as img:
            transposed = ImageOps.exif_transpose(img)
            if transposed is not None:
                img = transposed

            orig_w, orig_h = img.size
            thumb_w = max(1, int(round(orig_w * 0.5)))
            thumb_h = max(1, int(round(orig_h * 0.5)))

            thumb = img.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)

            ext_lower = ext.lower()
            if ext_lower in (".jpg", ".jpeg"):
                if thumb.mode in ("RGBA", "LA", "P"):
                    thumb = thumb.convert("RGB")
                thumb.save(thm_path, format="JPEG", quality=85, optimize=True)
            elif ext_lower == ".png":
                thumb.save(thm_path, format="PNG", optimize=True)
            elif ext_lower == ".webp":
                thumb.save(thm_path, format="WEBP", quality=85)
            elif ext_lower == ".gif":
                thumb.save(thm_path, format="GIF")
            else:
                thumb.save(thm_path)

        logger.info(f"Saved original ({org_filename}) and thumbnail ({thm_filename})")
        return raw_filename, None

    except Exception as e:
        logger.error(f"Failed to process and save profile image: {e}")
        for p in (org_path, thm_path):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        return None, f"Failed to save image file: {str(e)}"


def delete_profile_image(filename: str) -> bool:
    """
    Safely delete profile image files (both org_ and thm_, as well as legacy unprefixed)
    from static/assets/user-img/.
    Rules:
    - Never delete default.svg or empty/null filenames.
    - Check if another user still references the same filename.
    - Delete org_{filename} and thm_{filename} (and legacy {filename} if present).
    - Ignore missing file errors gracefully.
    """
    if not filename:
        return False

    clean_filename = os.path.basename(filename).strip()
    if not clean_filename or clean_filename.lower() == DEFAULT_PROFILE_IMAGE.lower():
        logger.info(f"Skipping deletion of default or empty image: {clean_filename}")
        return False

    # Normalize to base filename without org_ or thm_ prefix
    base_filename = clean_filename
    if base_filename.startswith("org_"):
        base_filename = base_filename[4:]
    elif base_filename.startswith("thm_"):
        base_filename = base_filename[4:]

    # Check if another user still references this image in DB
    try:
        from api.models.user import User
        referenced_count = User.query.filter(
            (User.profile == base_filename) | (User.profile == clean_filename)
        ).count()
        if referenced_count > 0:
            logger.info(f"Image {base_filename} is still referenced by {referenced_count} user(s). Skipping deletion.")
            return False
    except Exception as e:
        logger.warning(f"Could not verify image reference count in database: {e}")

    dest_dir = get_user_img_dir()
    candidates = [
        f"org_{base_filename}",
        f"thm_{base_filename}",
        base_filename,
    ]
    if clean_filename not in candidates:
        candidates.append(clean_filename)

    deleted_any = False
    for fname in set(candidates):
        file_path = os.path.join(dest_dir, fname)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Deleted profile image file: {fname}")
                deleted_any = True
            except OSError as e:
                logger.error(f"Error removing profile image file {file_path}: {e}")

    if not deleted_any:
        logger.warning(f"No profile image files found on disk for {clean_filename}. Skipping.")
    return deleted_any
