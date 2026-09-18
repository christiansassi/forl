"""Everything this widget asks of Windows.

Tkinter knows nothing about the taskbar, the desktop window manager, the
accessibility preference that decides whether the panel should animate, whether
a copy of the widget is already running, or what runs when the user signs in.
All the calls that fill those gaps live here, and every one of them degrades to
a sensible answer when the system call is unavailable, so an unusual build
costs a feature rather than the launch.

This is one of two backends behind the same set of names. Nothing above it
imports this module directly: they import the package, which picks the backend
that matches the machine.
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

from ..validation import require_non_empty_str, require_positive_int, require_type

ERROR_ALREADY_EXISTS = 183
# Per session rather than machine wide, so two signed-in users each get one.
MUTEX_NAMESPACE = "Local\\"

# Mutex handles are released when the process ends, so they only have to be kept
# from being garbage collected while it runs.
_HELD_MUTEXES: list[int] = []

SM_CXSMICON = 49
DEFAULT_SMALL_ICON = 16

SPI_GET_WORK_AREA = 0x0030
SPI_GET_CLIENT_AREA_ANIMATION = 0x1042

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2

PROCESS_SYSTEM_DPI_AWARE = 1


def detach(name: str) -> None:
	"""Put this process into the background and give the terminal back.

	Args:
		name: The name of this widget, which the macOS backend uses to name a log
			file and this one has no use for. str, non-empty.

	Returns:
		None. Nothing to do: the widget is launched with the windowed
		interpreter, which is given no console to hold in the first place.
	"""
	require_non_empty_str(name, "name")


def enable_dpi_awareness() -> None:
	"""Ask Windows to scale this process by the display, not to stretch it.

	Without this the whole interface is drawn at 96 dots per inch and blown up
	by the system, which is what makes text on a scaled display look soft.

	Returns:
		None. Does nothing when the call is unavailable, as on older builds.
	"""
	try:
		ctypes.windll.shcore.SetProcessDpiAwareness(PROCESS_SYSTEM_DPI_AWARE)
	except (AttributeError, OSError):
		pass


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


def small_icon_size() -> int:
	"""Return the edge length the shell draws a notification area icon at.

	Windows picks the frame of an icon closest to this size, so rendering at
	exactly it means the shell shows what was drawn rather than a resampling of
	something larger.

	Returns:
		int: The size in device pixels, which grows with the display scale, and
		16 when the system call is unavailable.
	"""
	try:
		size = ctypes.windll.user32.GetSystemMetrics(SM_CXSMICON)
	except (AttributeError, OSError):
		return DEFAULT_SMALL_ICON
	return size if size > 0 else DEFAULT_SMALL_ICON


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


# What starts the widget at sign-in. The run key of the current user needs no
# elevation, is the list Windows shows under startup apps so the user can see
# and undo it from outside the widget, and is per user, which matches a
# preference about one person's notification area.
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME_PREFIX = "FORL-"

ENTRY_SCRIPT = Path(__file__).resolve().parents[3] / "run.pyw"

# The interpreter that runs a script without opening a console window. Starting
# the widget with the plain interpreter would flash, or leave, a console at
# every sign-in.
WINDOWED_INTERPRETER = "pythonw.exe"
CONSOLE_INTERPRETER = "python.exe"


def entry_name(provider_key: str) -> str:
	"""Return the registry value name that holds one provider's startup entry.

	Args:
		provider_key: Key of the provider, such as "claude". str, non-empty.

	Returns:
		str: The value name.
	"""
	require_non_empty_str(provider_key, "provider_key")
	return f"{VALUE_NAME_PREFIX}{provider_key}"


def _interpreter() -> Path:
	"""Return the interpreter the startup entry should invoke.

	Returns:
		Path: The windowed interpreter beside the running one when it exists,
		otherwise the running interpreter itself.
	"""
	running = Path(sys.executable)
	if running.name.lower() == CONSOLE_INTERPRETER:
		windowed = running.with_name(WINDOWED_INTERPRETER)
		if windowed.exists():
			return windowed
	return running


def command_line(provider_key: str) -> str:
	"""Return the command Windows should run to start one provider's widget.

	Args:
		provider_key: Key of the provider, such as "claude". str, non-empty.

	Returns:
		str: The command line, with every path quoted as Windows expects.
	"""
	require_non_empty_str(provider_key, "provider_key")
	return subprocess.list2cmdline([str(_interpreter()), str(ENTRY_SCRIPT), f"--{provider_key}"])


def set_startup_entry(provider_key: str, enabled: bool) -> bool:
	"""Add or remove the entry that starts one provider's widget at sign-in.

	Args:
		provider_key: Key of the provider, such as "claude". str, non-empty.
		enabled: True to write the entry, False to remove it. bool.

	Returns:
		bool: True when the registry now says what was asked, including when the
		entry was already absent and removal was asked for. False when the
		registry could not be reached or written.
	"""
	require_non_empty_str(provider_key, "provider_key")
	require_type(enabled, bool, "enabled")

	try:
		import winreg
	except ImportError:
		return False

	name = entry_name(provider_key)
	try:
		with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
			if enabled:
				winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command_line(provider_key))
				return True
			try:
				winreg.DeleteValue(key, name)
			except FileNotFoundError:
				pass
			return True
	except OSError:
		return False
