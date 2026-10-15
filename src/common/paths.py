"""Where the widget keeps the files it writes for itself.

Two files live outside the tree, the preferences and the sign-ins, and both
belong in the same place: the directory a platform sets aside for one signed-in
user's application data. That directory is named differently on each platform,
so it is answered here once and both stores ask for it rather than each working
it out again.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .validation import require_non_empty_str

APP_DIR_NAME = "forl"

# Where macOS keeps the application data of one user, relative to the home
# directory. Named here rather than built from an environment variable, because
# macOS has none for it.
MACOS_DATA_DIR = ("Library", "Application Support")

# Where Linux keeps it when XDG_DATA_HOME is not set, as the XDG base directory
# specification says.
LINUX_DATA_DIR = (".local", "share")


def data_dir() -> Path:
	"""Return the directory this widget's own files belong in.

	The directory may not exist yet: a caller that writes creates it, and a
	caller that reads treats a missing file and a missing directory alike.

	Returns:
		Path: The per user application data directory of this widget, which is
		%APPDATA%\\forl on Windows, ~/Library/Application Support/forl on macOS,
		and $XDG_DATA_HOME/forl, by default ~/.local/share/forl, on Linux.
	"""
	if sys.platform == "darwin":
		return Path.home().joinpath(*MACOS_DATA_DIR) / APP_DIR_NAME
	if sys.platform == "win32":
		base = os.environ.get("APPDATA")
		return (Path(base) if base else Path.home()) / APP_DIR_NAME
	base = os.environ.get("XDG_DATA_HOME")
	root = Path(base) if base else Path.home().joinpath(*LINUX_DATA_DIR)
	return root / APP_DIR_NAME


def data_file(name: str) -> Path:
	"""Return the path of one file inside the application data directory.

	Args:
		name: File name, such as "settings.json". str, non-empty.

	Returns:
		Path: The full path, whose parent may not exist yet.
	"""
	require_non_empty_str(name, "name")
	return data_dir() / name
