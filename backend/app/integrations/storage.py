"""Private file storage. Local filesystem backend; references are relative keys, never user-supplied paths."""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from app.core.config import get_settings


class StorageError(Exception):
    pass


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents and p != self.root:
            raise StorageError("Invalid storage key")
        return p

    def save(self, prefix: str, data: bytes, suffix: str = "") -> str:
        if not re.fullmatch(r"[a-z0-9_\-/]+", prefix):
            raise StorageError("Invalid prefix")
        key = f"{prefix}/{uuid.uuid4().hex}{re.sub(r'[^a-z0-9.]', '', suffix.lower())}"
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
        return key

    def read(self, key: str) -> bytes:
        try:
            return self._resolve(key).read_bytes()
        except FileNotFoundError as e:
            raise StorageError("File not found") from e

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()

    def delete(self, key: str) -> None:
        try:
            self._resolve(key).unlink()
        except FileNotFoundError:
            pass


_storage: LocalStorage | None = None


def get_storage() -> LocalStorage:
    global _storage
    s = get_settings()
    if _storage is None or str(_storage.root) != str(Path(s.storage_path).resolve()):
        if s.storage_backend != "local":
            raise StorageError(f"Unsupported STORAGE_BACKEND '{s.storage_backend}' (only 'local' is implemented)")
        _storage = LocalStorage(s.storage_path)
    return _storage
