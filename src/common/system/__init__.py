"""The machine the widget is running on, behind one set of names.

Everything that is not portable lives in a platform backend: where the taskbar
or the top bar leaves room, which edge of the screen the panel opens from, how a
window is given the system chrome, which app mode the user chose, which type
face the interface is set in, how a second copy of the widget is kept from
starting, what runs at sign-in, how the icons are put in the notification area
or the tray, and where other programs may read the readings.

The backends live with their platforms, src/windows/backend.py and
src/linux/backend.py, and the entry point of each platform installs its own
here before anything else is imported. The shared code calls the functions
below and never learns which backend answered.

Adding a platform means writing one backend module with every name in
BACKEND_NAMES and installing it from that platform's entry point. Nothing in
the shared code changes.
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import Any, Callable

from ..validation import require_type

# Every name a backend module must provide.
BACKEND_NAMES = (
	"animations_enabled",
	"apply_panel_chrome",
	"claim_single_instance",
	"create_tray",
	"detach",
	"enable_dpi_awareness",
	"font_files",
	"panel_edge",
	"set_startup_entry",
	"status_dir",
	"tray_available",
	"ui_font_family",
	"uses_light_theme",
	"work_area",
)

# The two edges a panel can open from: next to a taskbar at the bottom of the
# screen, or under a top bar.
EDGE_BOTTOM = "bottom"
EDGE_TOP = "top"

_backend: ModuleType | None = None


def install(backend: ModuleType) -> None:
	"""Make one platform backend answer every call in this package.

	Args:
		backend: The platform's backend module, such as src.windows.backend.
			ModuleType providing every name in BACKEND_NAMES.

	Returns:
		None.
	"""
	global _backend
	require_type(backend, ModuleType, "backend")
	missing = [name for name in BACKEND_NAMES if not callable(getattr(backend, name, None))]
	if missing:
		raise ValueError(f"backend {backend.__name__} lacks {', '.join(missing)}")
	_backend = backend


def _active() -> ModuleType:
	"""Return the installed backend.

	Returns:
		ModuleType: The backend the entry point installed.
	"""
	if _backend is None:
		raise RuntimeError("no platform backend is installed; start the widget from a platform's main.py")
	return _backend


def animations_enabled() -> bool:
	"""Return whether the user allows interface animation.

	Returns:
		bool: True when animation is allowed, and True when the setting cannot be
		read.
	"""
	return _active().animations_enabled()


def apply_panel_chrome(window_handle: int, dark: bool) -> None:
	"""Give the panel window the corners and border the system draws for a mode.

	Args:
		window_handle: The native window handle of the panel. int.
		dark: Whether the panel is drawn in the dark mode. bool.

	Returns:
		None. Does nothing on a system that draws no such chrome.
	"""
	_active().apply_panel_chrome(window_handle, dark)


def claim_single_instance(name: str) -> bool:
	"""Claim a name for this process, and report whether it was free.

	Args:
		name: The name to claim, unique to what may run only once. str, non-empty.

	Returns:
		bool: True when this process now holds the name, False when another
		process already did.
	"""
	return _active().claim_single_instance(name)


def create_tray(
	name: str,
	draw: Callable[[float | None, int], Any],
	on_activate: Callable[[], None],
	on_menu: Callable[[int, int], None],
	on_quit: Callable[[], None],
) -> Any:
	"""Return a set of tray icons, one per displayed usage, none showing yet.

	Args:
		name: Prefix of every icon's name, such as a provider key, which must not
			change between runs. str, non-empty.
		draw: Returns the image of one icon, given its reading, or None before
			one, and its edge length in pixels. Callable taking a float or None
			and an int and returning a PIL.Image.Image.
		on_activate: Called on a left click, to open the panel. Callable taking
			no arguments and returning None.
		on_menu: Called with the pointer position on a right click, where the
			platform leaves the menu to the widget. Callable taking two ints and
			returning None.
		on_quit: Called when the user chooses Quit from a menu the system draws
			itself, where the platform does. Callable taking no arguments and
			returning None.

	Returns:
		The platform's tray manager, which has start(), sync(readings) and
		stop() methods.
	"""
	return _active().create_tray(name, draw, on_activate, on_menu, on_quit)


def detach(name: str) -> None:
	"""Put this process into the background and give the terminal back.

	Args:
		name: The name of this widget. str, non-empty.

	Returns:
		None.
	"""
	_active().detach(name)


def enable_dpi_awareness() -> None:
	"""Ask the system to scale this process by the display rather than stretch it.

	Returns:
		None.
	"""
	_active().enable_dpi_awareness()


def font_files(weight: str) -> tuple[str, ...]:
	"""Return the font files to try, in order, for type drawn into images.

	Args:
		weight: Either "normal" or "bold". str.

	Returns:
		tuple of str: Paths of TrueType or OpenType files, best first. Some may
		not exist on a given machine.
	"""
	return _active().font_files(weight)


def panel_edge() -> str:
	"""Return the edge of the screen the panel opens from.

	Returns:
		str: EDGE_BOTTOM next to a taskbar at the bottom, EDGE_TOP under a top
		bar.
	"""
	return _active().panel_edge()


def set_startup_entry(enabled: bool) -> bool:
	"""Add or remove what starts the widget when the user signs in.

	Args:
		enabled: True to add it, False to remove it. bool.

	Returns:
		bool: True when the system now says what was asked, False when it could
		not be changed.
	"""
	return _active().set_startup_entry(enabled)


def status_dir() -> Path | None:
	"""Return the directory the readings are written to for other programs, if any.

	Returns:
		Path or None: The directory status bars and desktop widgets read the
		readings from, or None on a platform where nothing reads them.
	"""
	return _active().status_dir()


def tray_available() -> bool:
	"""Return whether this session has a tray to put icons in.

	Returns:
		bool: True when icons can be shown. False when they cannot, in which case
		the panel is shown as an ordinary window instead.
	"""
	return _active().tray_available()


def ui_font_family() -> str:
	"""Return the family the interface text is set in.

	Returns:
		str: A family name Tk accepts.
	"""
	return _active().ui_font_family()


def uses_light_theme() -> bool:
	"""Return whether the user has chosen the light mode for applications.

	Returns:
		bool: True for the light mode, False for the dark mode.
	"""
	return _active().uses_light_theme()


def work_area(fallback_width: int, fallback_height: int) -> tuple[int, int, int, int]:
	"""Return the desktop rectangle not covered by a taskbar or a top bar.

	Args:
		fallback_width: Screen width to report when the system cannot say, in
			pixels. int, greater than 0.
		fallback_height: Screen height to report when the system cannot say, in
			pixels. int, greater than 0.

	Returns:
		tuple[int, int, int, int]: The work area as (left, top, right, bottom) in
		screen pixels.
	"""
	return _active().work_area(fallback_width, fallback_height)
