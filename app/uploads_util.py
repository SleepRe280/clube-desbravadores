import os
import uuid
from pathlib import Path

from werkzeug.utils import secure_filename

ALLOWED_EXT = frozenset({"png", "jpg", "jpeg", "webp"})


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def save_upload(file_storage, upload_folder: str, subfolder: str) -> str | None:
    if not file_storage or not file_storage.filename:
        return None
    fn = secure_filename(file_storage.filename)
    if not fn or not allowed_file(fn):
        return None
    ext = fn.rsplit(".", 1)[1].lower()
    name = f"{uuid.uuid4().hex}.{ext}"
    dest_dir = Path(upload_folder) / subfolder
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / name
    file_storage.save(str(path))
    return f"{subfolder}/{name}"
