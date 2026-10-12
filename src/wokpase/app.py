from __future__ import annotations

import asyncio
import difflib
import subprocess
from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, RichLog, Static, TextArea, Tree

from wokpase.config import AppConfig
from wokpase.providers import AIRequestError, generate
from wokpase.workspace import (
    IGNORED_DIRECTORIES,
    parse_file_response,
    read_text_file,
    safe_path,
)

LANGUAGES = {
    ".c": "c",
    ".cpp": "cpp",
    ".css": "css",
    ".go": "go",
    ".html": "html",
    ".java": "java",
    ".js": "javascript",
    ".json": "json",
    ".jsx": "javascript",
    ".md": "markdown",
    ".py": "python",
    ".rs": "rust",
    ".sh": "bash",
    ".sql": "sql",
    ".toml": "toml",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
}
COMMANDS = (":help", ":open", ":file", ":folder", ":save", ":run", ":ai", ":create-project")


def _edit_distance(left: str, right: str) -> int:
    distances = [[0] * (len(right) + 1) for _ in range(len(left) + 1)]
    for left_index in range(len(left) + 1):
        distances[left_index][0] = left_index
    for right_index in range(len(right) + 1):
        distances[0][right_index] = right_index
    for left_index in range(1, len(left) + 1):
        for right_index in range(1, len(right) + 1):
            distances[left_index][right_index] = min(
                min(
                    distances[left_index][right_index - 1] + 1,
                    distances[left_index - 1][right_index] + 1,
                    distances[left_index - 1][right_index - 1]
                    + (left[left_index - 1] != right[right_index - 1]),
                ),
                distances[left_index - 2][right_index - 2] + 1
                if (
                    left_index > 1
                    and right_index > 1
                    and left[left_index - 1] == right[right_index - 2]
                    and left[left_index - 2] == right[right_index - 1]
                )
                else len(left) + len(right),
            )
    return distances[-1][-1]


class DiffScreen(ModalScreen[bool]):
    CSS = """
    DiffScreen { align: center middle; }
    #diff-dialog { width: 90%; height: 85%; border: round $accent; background: $surface; padding: 1; }
    #diff-content { height: 1fr; overflow-y: auto; }
    #diff-actions { height: 3; align-horizontal: right; }
    #diff-actions Button { margin-left: 1; }
    """

    def __init__(self, changes: dict[Path, str], workspace: Path) -> None:
        super().__init__()
        self.changes = changes
        self.workspace = workspace

    def compose(self) -> ComposeResult:
        with Vertical(id="diff-dialog"):
            yield Static("Tinjau perubahan AI — perubahan belum ditulis ke disk")
            yield Static(self._render_diff(), id="diff-content")
            with Horizontal(id="diff-actions"):
                yield Button("Tolak (N)", id="reject")
                yield Button("Terima (Y)", variant="success", id="accept")

    def _render_diff(self) -> Text:
        output = Text()
        for path, new_content in self.changes.items():
            old_content = ""
            if path.exists():
                old_content = read_text_file(path)
            relative = path.relative_to(self.workspace)
            output.append(f"--- {relative}\n", style="bold red")
            output.append(f"+++ {relative}\n", style="bold green")
            diff = difflib.unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile="sebelum",
                tofile="sesudah",
            )
            for line in diff:
                style = "green" if line.startswith("+") else "red" if line.startswith("-") else ""
                output.append(line, style=style)
        return output

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "accept")

    def on_key(self, event) -> None:
        if event.key.lower() == "y":
            self.dismiss(True)
        elif event.key.lower() == "n":
            self.dismiss(False)


class WokpaseApp(App[None]):
    TITLE = "Wokpase"
    SUB_TITLE = "AI Coding Workspace"
    CSS = """
    Screen { layout: vertical; }
    #workspace { height: 1fr; }
    #logs-panel { width: 27%; min-width: 25; border: round $primary; }
    #editor-panel { width: 1fr; border: round $primary; }
    #files-panel { width: 25%; min-width: 22; border: round $primary; }
    .panel-title { height: 1; padding-left: 1; background: $primary-background; color: $text; }
    #logs { height: 1fr; padding: 0 1; }
    #file-tree { height: 1fr; }
    #editor { height: 1fr; }
    #command { dock: bottom; }
    #status { height: 1; padding-left: 1; background: $boost; color: $text; }
    """
    BINDINGS = [
        Binding("ctrl+s", "save_file", "Save"),
        Binding("ctrl+k", "ai_edit", "AI edit"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, workspace: Path) -> None:
        super().__init__()
        self.workspace = workspace.resolve()
        self.config = AppConfig.load()
        self.active_file: Path | None = None
        self.ai_working = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="workspace"):
            with Vertical(id="logs-panel"):
                yield Static("AI LOGS / SHELL", classes="panel-title")
                yield RichLog(id="logs", wrap=True, markup=False)
            with Vertical(id="editor-panel"):
                yield Static("EDITOR", classes="panel-title")
                yield TextArea("", id="editor", show_line_numbers=True, soft_wrap=False)
            with Vertical(id="files-panel"):
                yield Static("FILES", classes="panel-title")
                yield Tree(self.workspace.name, id="file-tree")
        yield Static("", id="status")
        yield Input(placeholder=":help untuk perintah", id="command")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_tree()
        self._log(f"[Wokpase] Workspace: {self.workspace}")
        self._log("[Wokpase] :help untuk perintah. Ctrl+K untuk edit AI.")
        self._update_status()
        self.query_one("#command", Input).focus()

    def _log(self, message: str) -> None:
        self.query_one("#logs", RichLog).write(message)

    def _update_status(self) -> None:
        filename = str(self.active_file.relative_to(self.workspace)) if self.active_file else "[No file]"
        state = "Working" if self.ai_working else "Idle"
        self.query_one("#status", Static).update(f" {filename}  |  AI: {state}  |  Ctrl+S Save  Ctrl+K AI")

    def refresh_tree(self) -> None:
        tree = self.query_one("#file-tree", Tree)
        tree.clear()
        tree.root.set_label(self.workspace.name)
        tree.root.data = self.workspace
        tree.root.expand()

        def add_directory(node: Tree.Node, directory: Path, depth: int = 0) -> None:
            if depth >= 5:
                return
            try:
                entries = sorted(directory.iterdir(), key=lambda item: (item.is_file(), item.name.lower()))
            except OSError as error:
                self._log(f"[File tree] Tidak dapat membaca {directory}: {error}")
                return
            for entry in entries:
                if entry.name in IGNORED_DIRECTORIES:
                    continue
                if entry.is_symlink() and self.workspace not in entry.resolve().parents:
                    continue
                child = node.add(entry.name, data=entry)
                if entry.is_dir():
                    add_directory(child, entry, depth + 1)

        add_directory(tree.root, self.workspace)

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        path = event.node.data
        if isinstance(path, Path) and path.is_file():
            self.open_file(path)

    def open_file(self, path: Path) -> None:
        try:
            content = read_text_file(path)
        except (OSError, ValueError) as error:
            self._log(f"[Error] {error}")
            return
        self.active_file = path
        editor = self.query_one("#editor", TextArea)
        editor.language = LANGUAGES.get(path.suffix.lower())
        editor.load_text(content)
        self._update_status()
        self._log(f"[Editor] Membuka {path.relative_to(self.workspace)}")
        editor.focus()

    def action_save_file(self) -> None:
        if self.active_file is None:
            self._log("[Save] Pilih berkas terlebih dahulu.")
            return
        try:
            self.active_file.write_text(self.query_one("#editor", TextArea).text, encoding="utf-8")
        except OSError as error:
            self._log(f"[Save] Gagal: {error}")
            return
        self._log(f"[Save] Tersimpan: {self.active_file.relative_to(self.workspace)}")

    def action_ai_edit(self) -> None:
        command = self.query_one("#command", Input)
        command.value = ":ai "
        command.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        command = event.value.strip()
        event.input.value = ""
        if command:
            self._dispatch(command)

    def _dispatch(self, command: str) -> None:
        name, _, argument = command.partition(" ")
        argument = argument.lstrip()
        if name.startswith(":") and name not in COMMANDS:
            distances = {candidate: _edit_distance(name, candidate) for candidate in COMMANDS}
            nearest_distance = min(distances.values())
            threshold = min(2, max(1, len(name) // 4))
            nearest = [
                candidate
                for candidate, distance in distances.items()
                if distance == nearest_distance
            ]
            if nearest_distance <= threshold and len(nearest) == 1:
                corrected = nearest[0]
                self._log(f"[Command] Autocorrect: {name} → {corrected}")
                self._dispatch(f"{corrected} {argument}" if argument else corrected)
                return
        if name == ":help":
            self._log(
                "[Help] :open PATH | :file PATH | :folder PATH | :save | "
                ":run COMMAND | :ai INSTRUCTION | :create-project DESCRIPTION | :help"
            )
        elif name == ":open":
            try:
                self.open_file(safe_path(self.workspace, argument))
            except ValueError as error:
                self._log(f"[Open] {error}")
        elif name in {":file", ":new-file"}:
            self.create_file(argument)
        elif name in {":folder", ":new-folder"}:
            self.create_folder(argument)
        elif name == ":save":
            self.action_save_file()
        elif name == ":run":
            if not argument:
                self._log("[Shell] Gunakan :run COMMAND")
            else:
                self.run_shell(argument)
        elif name == ":ai":
            if not argument:
                self._log("[AI] Berikan instruksi, misalnya :ai jelaskan kode ini")
            elif self.active_file is None:
                self._log("[AI] Buka berkas terlebih dahulu.")
            else:
                self.edit_with_ai(argument)
        elif name == ":create-project":
            if not argument:
                self._log("[AI] Gunakan :create-project deskripsi proyek")
            else:
                self.create_project(argument)
        else:
            self._log(f"[Command] Perintah tidak dikenal: {name}. Ketik :help.")

    def create_file(self, relative_path: str) -> None:
        if not relative_path:
            self._log("[File] Gunakan :file PATH")
            return
        try:
            path = safe_path(self.workspace, relative_path)
            if path == self.workspace:
                raise ValueError("path harus menunjuk ke berkas di dalam workspace")
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8"):
                pass
        except (OSError, ValueError) as error:
            self._log(f"[File] Gagal membuat {relative_path}: {error}")
            return
        self.refresh_tree()
        self.open_file(path)
        self._log(f"[File] Dibuat: {path.relative_to(self.workspace)}")

    def create_folder(self, relative_path: str) -> None:
        if not relative_path:
            self._log("[Folder] Gunakan :folder PATH")
            return
        try:
            path = safe_path(self.workspace, relative_path)
            if path == self.workspace:
                raise ValueError("path harus menunjuk ke folder di dalam workspace")
            path.mkdir(parents=True, exist_ok=False)
        except (OSError, ValueError) as error:
            self._log(f"[Folder] Gagal membuat {relative_path}: {error}")
            return
        self.refresh_tree()
        self._log(f"[Folder] Dibuat: {path.relative_to(self.workspace)}")

    @work(exclusive=True)
    async def run_shell(self, command: str) -> None:
        self._log(f"$ {command}")
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=self.workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            output, _ = await asyncio.wait_for(process.communicate(), timeout=120)
            text = output.decode("utf-8", errors="replace").strip()
            if text:
                self._log(text)
            self._log(f"[Shell] Exit code: {process.returncode}")
        except asyncio.TimeoutError:
            self._log("[Shell] Perintah dihentikan setelah batas 120 detik.")
        except OSError as error:
            self._log(f"[Shell] Gagal menjalankan perintah: {error}")
        finally:
            self.refresh_tree()

    @work(exclusive=True)
    async def edit_with_ai(self, instruction: str) -> None:
        if self.active_file is None:
            return
        path = self.active_file
        self.ai_working = True
        self._update_status()
        self._log(f"[{self.config.executor.provider}] Mengedit {path.relative_to(self.workspace)}...")
        original = self.query_one("#editor", TextArea).text
        prompt = (
            "You are a careful coding assistant. Return ONLY valid JSON in this exact shape: "
            '{"files":[{"path":"relative/path","content":"complete file content"}]}. '
            "Do not include markdown fences. Preserve unrelated behavior. "
            f"Edit only this file: {path.relative_to(self.workspace)}\n"
            f"User instruction: {instruction}\n"
            f"Current file content:\n{original}"
        )
        try:
            response = await asyncio.to_thread(generate, self.config, self.config.executor, prompt)
            files = parse_file_response(response)
            if set(files) != {str(path.relative_to(self.workspace))}:
                raise ValueError("AI mengembalikan berkas di luar berkas aktif")
            changes = {path: files[str(path.relative_to(self.workspace))]}
            self._review_changes(changes)
        except (AIRequestError, OSError, ValueError) as error:
            self._log(f"[AI] Gagal: {error}")
        finally:
            self.ai_working = False
            self._update_status()

    @work(exclusive=True)
    async def create_project(self, description: str) -> None:
        self.ai_working = True
        self._update_status()
        self._log(f"[{self.config.planner.provider}] Merencanakan proyek...")
        try:
            plan = await asyncio.to_thread(
                generate,
                self.config,
                self.config.planner,
                "Create a concise implementation plan for the requested software project. "
                "Mention intended files and technologies. Do not output code.\n"
                f"Project request: {description}",
            )
            self._log(f"[Plan]\n{plan}")
            prompt = (
                "Implement the project from this plan. Return ONLY valid JSON shaped as "
                '{"files":[{"path":"relative/path","content":"complete file content"}]}. '
                "No markdown fences. Paths must be relative to the workspace. "
                "Do not emit binaries or write outside the project.\n"
                f"Project request: {description}\nPlan:\n{plan}"
            )
            self._log(f"[{self.config.executor.provider}] Menulis berkas proyek...")
            response = await asyncio.to_thread(generate, self.config, self.config.executor, prompt)
            files = parse_file_response(response)
            changes = {safe_path(self.workspace, relative): content for relative, content in files.items()}
            self._review_changes(changes)
        except (AIRequestError, OSError, ValueError) as error:
            self._log(f"[AI] Gagal: {error}")
        finally:
            self.ai_working = False
            self._update_status()

    def _review_changes(self, changes: dict[Path, str]) -> None:
        if not changes:
            self._log("[AI] Tidak ada perubahan untuk ditinjau.")
            return

        def apply_changes(accepted: bool) -> None:
            if not accepted:
                self._log("[Diff] Perubahan ditolak; workspace tidak berubah.")
                return
            try:
                for path, content in changes.items():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content, encoding="utf-8")
                self.refresh_tree()
                if self.active_file in changes:
                    self.open_file(self.active_file)
                self._log(f"[Diff] {len(changes)} berkas diterima dan disimpan.")
            except OSError as error:
                self._log(f"[Diff] Gagal menyimpan perubahan: {error}")

        self.push_screen(DiffScreen(changes, self.workspace), callback=apply_changes)
