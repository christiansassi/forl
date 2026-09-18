"""Build the Windows executable using the current Python environment."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

WINDOWS_DIR = Path(__file__).resolve().parent
ROOT_DIR = WINDOWS_DIR.parents[1]
BUILD_DIR = WINDOWS_DIR / ".build"
DIST_DIR = WINDOWS_DIR / "dist"


def main() -> int:
	"""Package the windowed executable with the installed dependencies.

	Returns:
		int: Zero on success, or a nonzero status when a build step fails.
	"""
	if sys.platform != "win32":
		print("Build FORL.exe on Windows with Python 3.10 or newer.", file=sys.stderr)
		return 1
	if sys.version_info < (3, 10):
		print("Python 3.10 or newer is required.", file=sys.stderr)
		return 1
	try:
		environment = os.environ.copy()
		environment["PYINSTALLER_CONFIG_DIR"] = str(BUILD_DIR / "cache")
		subprocess.run([
			sys.executable, "-m", "PyInstaller",
			"--noconfirm", "--onefile", "--windowed", "--name", "FORL",
			"--distpath", str(DIST_DIR),
			"--workpath", str(BUILD_DIR / "work"),
			"--specpath", str(BUILD_DIR),
			"--paths", str(ROOT_DIR),
			"--add-data", f"{ROOT_DIR / 'src' / 'common' / 'assets'}:src/common/assets",
			"--hidden-import", "pystray._win32",
			str(WINDOWS_DIR / "main.py"),
		], cwd=WINDOWS_DIR, env=environment, check=True)
	except (OSError, subprocess.CalledProcessError) as error:
		print(f"Build failed: {error}", file=sys.stderr)
		return 1
	print(f"Built {DIST_DIR / 'FORL.exe'}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
