"""``python -m flex``: the CLI without flex.exe, which Windows file-locks while it runs."""

from flex.cli import app

if __name__ == "__main__":
    app()
