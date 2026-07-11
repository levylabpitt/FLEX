"""Lets ``python -m flex`` run the CLI without going through the ``flex.exe``
console-script launcher, which stays open (and file-locked, on Windows) for
the life of any long-running command like ``dashboard`` -- blocking package
installs into the same environment while it runs.
"""

from flex.cli import app

if __name__ == "__main__":
    app()
