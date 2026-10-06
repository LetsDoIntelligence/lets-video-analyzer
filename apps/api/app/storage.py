"""Filesystem storage for uploaded videos."""

import re
from pathlib import Path

from fastapi import UploadFile

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}
CHUNK = 1024 * 1024


class StorageError(Exception):
    """Raised for rejected uploads; `status_code` maps to the HTTP response."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def clean_name(filename: str) -> str:
    """Display name: basename without extension, control characters removed."""
    base = Path(filename.replace("\\", "/")).name
    stem = re.sub(r"[\x00-\x1f]", "", Path(base).stem).strip()
    return stem[:255] or "Untitled video"


def validate_upload(file: UploadFile) -> str:
    """Return the lower-cased extension, or raise StorageError."""
    ext = Path((file.filename or "").replace("\\", "/")).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise StorageError("Unsupported file type. Use MP4, MOV, WebM, MKV or AVI.", 415)
    if file.content_type and not (
        file.content_type.startswith("video/") or file.content_type == "application/octet-stream"
    ):
        raise StorageError("That file doesn't look like a video.", 415)
    return ext


async def save_upload(file: UploadFile, dest: Path, max_bytes: int) -> int:
    """Stream the upload to `dest`; return its size. Cleans up on failure."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with dest.open("wb") as out:
            while chunk := await file.read(CHUNK):
                size += len(chunk)
                if size > max_bytes:
                    raise StorageError(f"File is too large (limit {max_bytes // 1024**2} MB).", 413)
                out.write(chunk)
        if size == 0:
            raise StorageError("The uploaded file is empty.", 400)
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return size


def resolve_inside(data_dir: Path, relative: str) -> Path:
    """Resolve a stored relative path, refusing anything that escapes `data_dir`."""
    root = data_dir.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise StorageError("Invalid storage path.", 500)
    return path
