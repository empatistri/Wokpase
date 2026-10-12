from __future__ import annotations

import json
from pathlib import Path
from typing import Any


IGNORED_DIRECTORIES = {".git", ".venv", "__pycache__", "node_modules"}


class FileResponseSyntaxError(ValueError):
    """The AI response does not contain syntactically valid file JSON."""


def safe_path(root: Path, relative_path: str) -> Path:
    root = root.resolve()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("path berada di luar workspace")
    return candidate


def parse_file_response(response: str) -> dict[str, str]:
    content = response.strip().lstrip("\ufeff")
    data: Any = None
    try:
        data = json.loads(content)
    except json.JSONDecodeError as direct_error:
        decoder = json.JSONDecoder()
        for start in (index for index, char in enumerate(content) if char == "{"):
            try:
                candidate, _ = decoder.raw_decode(content, start)
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict) and isinstance(candidate.get("files"), list):
                data = candidate
                break
        if data is None:
            excerpt = content[:120].replace("\n", "\\n")
            raise FileResponseSyntaxError(
                "respons AI bukan JSON valid "
                f"(baris {direct_error.lineno}, kolom {direct_error.colno}); "
                f"awal respons: {excerpt!r}"
            ) from direct_error
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
