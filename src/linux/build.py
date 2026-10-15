"""Build the Linux executable using the current Python environment.

One command makes one file, src/linux/dist/FORL, with Python, Tk, the libraries
and the artwork inside it, so it runs on a machine that has none of them
installed. Copy it anywhere and run it.

What PyInstaller prints is all that is printed: the build reports its own
progress, warnings and result, and nothing is added around it. The only lines
this script writes itself are the ones that explain why a build cannot start at
all: on another platform, on a Python too old to run the widget, or on a Python
without Tk.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

LINUX_DIR = Path(__file__).resolve().parent
ROOT_DIR = LINUX_DIR.parents[1]
BUILD_DIR = LINUX_DIR / ".build"
DIST_DIR = LINUX_DIR / "dist"
ASSETS_DIR = ROOT_DIR / "src" / "common" / "assets"


def main() -> int:
	"""Package the executable with the installed dependencies.

	Returns:
		int: The exit status of PyInstaller, which is zero on success, or 1 when
		the build cannot start on this machine.
	"""
	if not sys.platform.startswith("linux"):
		print("Build FORL on Linux with Python 3.10 or newer.", file=sys.stderr)
		return 1
	if sys.version_info < (3, 10):
		print("Python 3.10 or newer is required.", file=sys.stderr)
		return 1
	try:
		import tkinter  # noqa: F401
	except ImportError:
		print("This Python has no Tk. Install your distribution's python3-tk (python3-tkinter on Fedora, tk on Arch).", file=sys.stderr)
		return 1
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
		"--add-data", f"{ASSETS_DIR}:src/common/assets",
		# The KDE Plasma widget, which the executable installs on a Plasma desktop.
		"--add-data", f"{LINUX_DIR / 'plasma'}:src/linux/plasma",
		# The GNOME Shell extension, which the executable installs on GNOME.
		"--add-data", f"{LINUX_DIR / 'gnome'}:src/linux/gnome",
		"--hidden-import", "PIL._tkinter_finder",
		str(LINUX_DIR / "main.py"),
	], cwd=LINUX_DIR, env=environment).returncode


if __name__ == "__main__":
	raise SystemExit(main())
