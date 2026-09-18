"""The machine the widget is running on, behind one set of names.

Everything that is not portable lives in a backend: where the taskbar leaves
room, how large a tray icon is drawn, how a window is given the system chrome,
how a second copy of the widget is kept from starting, what runs at sign-in, and
how a widget started from a terminal gets out of it.
One backend is chosen here, once, by the platform, and the rest of the widget
imports these names without knowing which one answered.

Adding a platform means writing one module with these functions in it and naming
it below. Nothing above this package changes.
"""

from __future__ import annotations

import sys

WINDOWS = "windows"

# What sys.platform reports, mapped to the backend that serves it. macOS is not
# here: it has an application of its own under the mac directory, written in
# Swift, and a second half-answer on the same machine would only be in its way.
PLATFORM_NAMES = {
	"win32": WINDOWS,
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


# A platform with no backend cannot reach here, because the entry point stops
# before importing anything that needs one.
from .windows import (
	animations_enabled,
	apply_panel_chrome,
	claim_single_instance,
	detach,
	enable_dpi_awareness,
	set_startup_entry,
	small_icon_size,
	work_area,
)

__all__ = [
	"WINDOWS",
	"animations_enabled",
	"apply_panel_chrome",
	"claim_single_instance",
	"current",
	"detach",
	"enable_dpi_awareness",
	"is_supported",
	"set_startup_entry",
	"small_icon_size",
	"work_area",
]
