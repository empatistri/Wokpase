from __future__ import annotations

import argparse
from pathlib import Path

from wokpase.app import WokpaseApp


def main() -> None:
    parser = argparse.ArgumentParser(description="AI-powered terminal coding workspace")
    parser.add_argument("directory", nargs="?", default=".", help="workspace directory")
    args = parser.parse_args()
    workspace = Path(args.directory).expanduser().resolve()
    if not workspace.is_dir():
        parser.error(f"not a directory: {workspace}")
    WokpaseApp(workspace).run()


if __name__ == "__main__":
    main()
