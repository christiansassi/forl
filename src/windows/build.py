"""Build the Windows executable using the current Python environment.

What PyInstaller prints is all that is printed: the build reports its own
progress, warnings and result, and nothing is added around it. The only lines
this script writes itself are the two that explain why a build cannot start at
all, on another platform or on a Python too old to run the widget.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PIL import Image

WINDOWS_DIR = Path(__file__).resolve().parent
ROOT_DIR = WINDOWS_DIR.parents[1]
BUILD_DIR = WINDOWS_DIR / ".build"
DIST_DIR = WINDOWS_DIR / "dist"
SHARED_ICON = ROOT_DIR / "src" / "common" / "assets" / "icon.png"
ICON_SIZES = [16, 24, 32, 48, 64, 128, 256]


def build_icon() -> Path | None:
	"""Cut the shared app icon into the multi-size .ico Windows expects.

	The icon lives once, at src/common/assets/icon.png, so that the executable
	and the Mac app are built from the same artwork. Windows picks the frame
	closest to the size it is drawing, so every frame the shell asks for is
	written into one file rather than left to be scaled from a single bitmap.

	Returns:
		Path | None: The generated .ico, or None when the shared icon is absent,
			which builds an executable with the default Python icon.
	"""
	if not SHARED_ICON.is_file():
		return None
	BUILD_DIR.mkdir(parents=True, exist_ok=True)
	target = BUILD_DIR / "FORL.ico"
	with Image.open(SHARED_ICON) as source:
		source.convert("RGBA").save(target, format="ICO", sizes=[(size, size) for size in ICON_SIZES])
	return target


def main() -> int:
	"""Package the windowed executable with the installed dependencies.

	Returns:
		int: The exit status of PyInstaller, which is zero on success, or 1 when
		the build cannot start on this machine.
	"""
	if sys.platform != "win32":
		print("Build FORL.exe on Windows with Python 3.10 or newer.", file=sys.stderr)
		return 1
	if sys.version_info < (3, 10):
		print("Python 3.10 or newer is required.", file=sys.stderr)
		return 1
	icon = build_icon()
	environment = os.environ.copy()
	environment["PYINSTALLER_CONFIG_DIR"] = str(BUILD_DIR / "cache")
	# PyInstaller's own output is left to reach the console, and its exit
	# status is passed on: it already says what failed when something does.
	return subprocess.run([
		sys.executable, "-m", "PyInstaller",
		"--noconfirm", "--onefile", "--windowed", "--name", "FORL",
		"--distpath", str(DIST_DIR),
		"--workpath", str(BUILD_DIR / "work"),
		"--specpath", str(BUILD_DIR),
		"--paths", str(ROOT_DIR),
		"--add-data", f"{ROOT_DIR / 'src' / 'common' / 'assets'}:src/common/assets",
		"--hidden-import", "pystray._win32",
		*(["--icon", str(icon)] if icon else []),
		str(WINDOWS_DIR / "main.py"),
	], cwd=WINDOWS_DIR, env=environment).returncode


if __name__ == "__main__":
	raise SystemExit(main())
