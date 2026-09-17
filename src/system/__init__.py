"""The machine the widget is running on, behind one set of names.

Everything that is not portable lives in a backend: where the taskbar leaves
room, how large a tray icon is drawn, how a window is given the system chrome,
how a second copy of the widget is kept from starting, and what runs at sign-in.
One backend is chosen here, once, by the platform, and the rest of the widget
imports these names without knowing which one answered.

Adding a platform means writing one module with these functions in it and naming
it below. Nothing above this package changes.
"""

from __future__ import annotations

import sys

WINDOWS = "windows"
MACOS = "macos"

# What sys.platform reports, mapped to the backend that serves it.
PLATFORM_NAMES = {
	"win32": WINDOWS,
	"darwin": MACOS,
}


def current() -> str:
	"""Return the platform the widget is running on.

	Returns:
		str: WINDOWS, MACOS, or an empty string on a platform with no backend.
	"""
	return PLATFORM_NAMES.get(sys.platform, "")


def is_supported() -> bool:
	"""Return whether this machine has a backend at all.

	Returns:
		bool: True when the widget can run here.
	"""
	return bool(current())


if current() == MACOS:
	from .macos import (
		animations_enabled,
		apply_panel_chrome,
		claim_single_instance,
		enable_dpi_awareness,
		set_startup_entry,
		small_icon_size,
		work_area,
	)
else:
	# Windows is the fallback as well as a case of its own: a platform with no
	# backend cannot reach here, because the entry point stops before importing
	# anything that needs one.
	from .windows import (
		animations_enabled,
		apply_panel_chrome,
		claim_single_instance,
		enable_dpi_awareness,
		set_startup_entry,
		small_icon_size,
		work_area,
	)

__all__ = [
	"MACOS",
	"WINDOWS",
	"animations_enabled",
	"apply_panel_chrome",
	"claim_single_instance",
	"current",
	"enable_dpi_awareness",
	"is_supported",
	"set_startup_entry",
	"small_icon_size",
	"work_area",
]
