"""Windows integration.

Tkinter knows nothing about the taskbar, the desktop window manager, the
accessibility preference that decides whether the panel should animate, or
whether a copy of the widget is already running. All the calls that fill those
gaps live here, and every one of them degrades to a sensible answer when the
system call is unavailable.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from ..validation import require_non_empty_str, require_positive_int, require_type

ERROR_ALREADY_EXISTS = 183
# Per session rather than machine wide, so two signed-in users each get one.
MUTEX_NAMESPACE = "Local\\"

# Mutex handles are released when the process ends, so they only have to be kept
# from being garbage collected while it runs.
_HELD_MUTEXES: list[int] = []

SPI_GET_WORK_AREA = 0x0030
SPI_GET_CLIENT_AREA_ANIMATION = 0x1042

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2


def claim_single_instance(name: str) -> bool:
	"""Claim a name for this process, and report whether it was free.

	Claimed through a named mutex, which Windows releases when the process ends,
	so a widget that is killed or crashes does not keep the name locked.

	Args:
		name: The name to claim, unique to what may run only once. str, non-empty.

	Returns:
		bool: True when this process now holds the name, False when another
		process already did. True when the system call is unavailable, since a
		machine that cannot answer should not be stopped from running the widget.
	"""
	require_non_empty_str(name, "name")
	try:
		kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
		handle = kernel32.CreateMutexW(None, False, MUTEX_NAMESPACE + name)
	except (AttributeError, OSError):
		return True
	if not handle:
		return True
	if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
		return False
	_HELD_MUTEXES.append(handle)
	return True


def work_area(fallback_width: int, fallback_height: int) -> tuple[int, int, int, int]:
	"""Return the desktop rectangle that is not covered by the taskbar.

	Args:
		fallback_width: Screen width to report when the system call fails, in
			pixels. int, greater than 0.
		fallback_height: Screen height to report when the system call fails, in
			pixels. int, greater than 0.

	Returns:
		tuple[int, int, int, int]: The work area as (left, top, right, bottom) in
		screen pixels.
	"""
	require_positive_int(fallback_width, "fallback_width")
	require_positive_int(fallback_height, "fallback_height")

	rect = wintypes.RECT()
	try:
		ok = ctypes.windll.user32.SystemParametersInfoW(SPI_GET_WORK_AREA, 0, ctypes.byref(rect), 0)
	except (AttributeError, OSError):
		ok = 0
	if not ok or rect.right <= rect.left or rect.bottom <= rect.top:
		return (0, 0, fallback_width, fallback_height)
	return (rect.left, rect.top, rect.right, rect.bottom)


def animations_enabled() -> bool:
	"""Return whether the user allows interface animation.

	This is the Windows equivalent of the reduced motion preference: it is off
	when the user turns off "Animation effects" in accessibility settings.

	Returns:
		bool: True when animation is allowed, and True when the setting cannot
		be read.
	"""
	enabled = wintypes.BOOL()
	try:
		ok = ctypes.windll.user32.SystemParametersInfoW(
			SPI_GET_CLIENT_AREA_ANIMATION, 0, ctypes.byref(enabled), 0
		)
	except (AttributeError, OSError):
		return True
	return bool(enabled.value) if ok else True


def _set_window_attribute(window_handle: int, attribute: int, value: int) -> bool:
	"""Set one desktop window manager attribute on a window.

	Args:
		window_handle: The native window handle. int.
		attribute: The DWMWA constant to set. int.
		value: The integer value to set it to. int.

	Returns:
		bool: True when the call succeeded.
	"""
	try:
		result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
			wintypes.HWND(window_handle),
			ctypes.c_uint(attribute),
			ctypes.byref(ctypes.c_int(value)),
			ctypes.sizeof(ctypes.c_int),
		)
	except (AttributeError, OSError):
		return False
	return result == 0


def apply_panel_chrome(window_handle: int) -> None:
	"""Give a window rounded corners and the dark window manager treatment.

	Rounding is done by the desktop window manager rather than by masking the
	window, so the corners are composited with the wallpaper behind them and stay
	smooth at any display scale. Both calls are advisory: on a build that does
	not support them the window simply keeps square corners.

	Args:
		window_handle: The native window handle of the panel. int.

	Returns:
		None.
	"""
	require_type(window_handle, int, "window_handle")
	_set_window_attribute(window_handle, DWMWA_USE_IMMERSIVE_DARK_MODE, 1)
	_set_window_attribute(window_handle, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)
