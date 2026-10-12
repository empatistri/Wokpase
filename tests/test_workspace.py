import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from wokpase.app import DiffScreen, WokpaseApp
from wokpase.config import AgentConfig, AppConfig
from wokpase.providers import AIRequestError, generate
from wokpase.workspace import parse_file_response, safe_path


def test_safe_path_keeps_paths_inside_workspace(tmp_path: Path) -> None:
    assert safe_path(tmp_path, "src/main.py") == tmp_path / "src" / "main.py"


def test_safe_path_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="di luar workspace"):
        safe_path(tmp_path, "../outside.txt")


def test_openrouter_free_model_uses_free_router(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WOKPASE_OPENROUTER_KEY", "test-key")
    response = {"choices": [{"message": {"content": "Hello"}}]}
    with patch("wokpase.providers._post_json", return_value=response) as post_json:
        result = generate(
            AppConfig(AgentConfig("openrouter", "openrouter/free"),
                      AgentConfig("openrouter", "openrouter/free")),
            AgentConfig("openrouter", "openrouter/free"),
            "test prompt",
        )

    assert result == "Hello"
    args, kwargs = post_json.call_args
    assert args[0] == "https://openrouter.ai/api/v1/chat/completions"
    assert args[1]["model"] == "openrouter/free"
    assert args[2] == {"Authorization": "Bearer test-key"}


def test_openrouter_rejects_paid_model_before_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WOKPASE_OPENROUTER_KEY", "test-key")
    agent = AgentConfig("openrouter", "anthropic/claude-sonnet")
    config = AppConfig(agent, agent)
    with patch("wokpase.providers._post_json") as post_json:
        with pytest.raises(AIRequestError, match="hanya menerima model gratis"):
            generate(config, agent, "test prompt")
    post_json.assert_not_called()


def test_openrouter_accepts_explicit_free_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WOKPASE_OPENROUTER_KEY", "test-key")
    response = {"choices": [{"message": {"content": "Free response"}}]}
    agent = AgentConfig("openrouter", "meta-llama/llama-3.2-3b-instruct:free")
    with patch("wokpase.providers._post_json", return_value=response) as post_json:
        assert generate(AppConfig(agent, agent), agent, "prompt") == "Free response"
    assert post_json.call_args.args[1]["model"].endswith(":free")


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


def test_new_file_and_folder_commands_update_tree(tmp_path: Path) -> None:
    app = WokpaseApp(tmp_path)

    async def exercise_commands() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()
            app._dispatch(":folder src/components")
            app._dispatch(":file src/components/Header.py")
            await pilot.pause()

            new_file = tmp_path / "src/components/Header.py"
            assert new_file.is_file()
            assert app.query_one("#editor").text == ""
            assert app.active_file == new_file

            tree = app.query_one("#file-tree")
            src_node = next(node for node in tree.root.children if str(node.label) == "src")
            components_node = next(
                node for node in src_node.children if str(node.label) == "components"
            )
            assert any(str(node.label) == "Header.py" for node in components_node.children)

    asyncio.run(exercise_commands())


@pytest.mark.parametrize(
    "command, expected_path",
    [
        (":flie src/main.py", "src/main.py"),
        (":foler src/components", "src/components"),
    ],
)
def test_command_autocorrect_keeps_arguments(
    tmp_path: Path, command: str, expected_path: str
) -> None:
    app = WokpaseApp(tmp_path)

    async def exercise_autocorrect() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()
            app._dispatch(command)
            await pilot.pause()
            assert (tmp_path / expected_path).exists()

    asyncio.run(exercise_autocorrect())


@pytest.mark.parametrize("command", [":file", ":folder"])
def test_create_commands_reject_workspace_escape(tmp_path: Path, command: str) -> None:
    app = WokpaseApp(tmp_path)
    outside = tmp_path.parent / "outside-wokpase-test"

    async def exercise_command() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()
            app._dispatch(f"{command} ../outside-wokpase-test")
            await pilot.pause()
            assert not outside.exists()

    asyncio.run(exercise_command())


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


def test_ai_edit_updates_status_while_diff_screen_is_open(tmp_path: Path) -> None:
    source = tmp_path / "hello.py"
    source.write_text("", encoding="utf-8")
    app = WokpaseApp(tmp_path)

    async def exercise_ai_edit() -> None:
        with patch(
            "wokpase.app.generate",
            return_value='{"files":[{"path":"hello.py","content":"print(1)\\n"}]}',
        ):
            async with app.run_test() as pilot:
                await pilot.pause()
                app.open_file(source)
                app.edit_with_ai("add print")
                await pilot.pause(0.2)

                assert isinstance(app.screen, DiffScreen)
                status = app.screen_stack[0].query_one("#status")
                assert "AI: Idle" in str(status.render())

                await pilot.press("y")
                await pilot.pause()
                assert source.read_text(encoding="utf-8") == "print(1)\n"

    asyncio.run(exercise_ai_edit())
