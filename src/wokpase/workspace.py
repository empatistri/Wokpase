from __future__ import annotations

import json
from pathlib import Path
from typing import Any


IGNORED_DIRECTORIES = {".git", ".venv", "__pycache__", "node_modules"}


def safe_path(root: Path, relative_path: str) -> Path:
    root = root.resolve()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("path berada di luar workspace")
    return candidate


def parse_file_response(response: str) -> dict[str, str]:
    content = response.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
        if content.endswith("```"):
            content = content[:-3].strip()
    try:
        data: Any = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError(f"respons AI bukan JSON valid: {error}") from error
    if not isinstance(data, dict) or not isinstance(data.get("files"), list):
        raise ValueError("respons AI harus berbentuk {\"files\": [...]}")

    files: dict[str, str] = {}
    for item in data["files"]:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError("setiap berkas harus memiliki path dan content")
        path = item["path"]
        text = item.get("content")
        if not isinstance(text, str) or not path or Path(path).is_absolute():
            raise ValueError("path berkas harus relatif dan content harus berupa teks")
        if ".." in Path(path).parts:
            raise ValueError("path traversal tidak diperbolehkan")
        files[path] = text
    if not files:
        raise ValueError("AI tidak menghasilkan berkas apa pun")
    return files


def read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"berkas bukan teks UTF-8: {path.name}") from error
