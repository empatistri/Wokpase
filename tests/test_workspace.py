import asyncio
from pathlib import Path

import pytest

from wokpase.app import WokpaseApp
from wokpase.workspace import parse_file_response, safe_path


def test_safe_path_keeps_paths_inside_workspace(tmp_path: Path) -> None:
    assert safe_path(tmp_path, "src/main.py") == tmp_path / "src" / "main.py"


def test_safe_path_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="di luar workspace"):
        safe_path(tmp_path, "../outside.txt")


def test_parse_file_response_accepts_json_and_markdown_fence() -> None:
    response = '```json\n{"files":[{"path":"hello.py","content":"print(1)"}]}\n```'
    assert parse_file_response(response) == {"hello.py": "print(1)"}


@pytest.mark.parametrize(
    "response",
    [
        '{"files":[{"path":"../outside.py","content":"bad"}]}',
        '{"files":[{"path":"/tmp/outside.py","content":"bad"}]}',
        '{"files":[]}',
        "not json",
    ],
)
def test_parse_file_response_rejects_unsafe_or_invalid_data(response: str) -> None:
    with pytest.raises(ValueError):
        parse_file_response(response)


def test_tui_starts_and_opens_workspace_file(tmp_path: Path) -> None:
    source = tmp_path / "hello.py"
    source.write_text("print('hello')\n", encoding="utf-8")
    app = WokpaseApp(tmp_path)

    async def exercise_app() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()
            app.open_file(source)
            assert app.query_one("#editor").text == "print('hello')\n"
            assert app.query_one("#editor").language == "python"
            await pilot.press("ctrl+s")
            await pilot.pause()
            assert source.read_text(encoding="utf-8") == "print('hello')\n"

    asyncio.run(exercise_app())


@pytest.mark.parametrize("key, accepted", [("y", True), ("n", False)])
def test_ai_diff_requires_acceptance(tmp_path: Path, key: str, accepted: bool) -> None:
    target = tmp_path / "new.py"
    app = WokpaseApp(tmp_path)

    async def exercise_diff() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()
            app._review_changes({target: "print('generated')\n"})
            await pilot.pause()
            await pilot.press(key)
            await pilot.pause()
            assert target.exists() is accepted
            if accepted:
                assert target.read_text(encoding="utf-8") == "print('generated')\n"

    asyncio.run(exercise_diff())
