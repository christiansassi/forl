"""Everything this widget will ask of macOS.

This is the second backend behind the names the rest of the widget calls. It is
a stub: every function here answers the way the Windows backend answers when a
system call is unavailable, which is the answer that costs a feature rather than
the launch. Nothing here raises, so the shared code above can run unchanged
while the macOS parts are filled in one at a time.

The reading is meant to appear in three places on macOS rather than the one
place Windows gives it: an item in the menu bar, a badge on the Dock icon, and a
widget on the desktop. Only the first is the same shape as the notification area
icon the shared code already drives, so the other two will want surfaces of
their own above this layer. What belongs here is only what each of them has to
ask the system for.

What each function will eventually be:

	work_area          the visible frame of the main screen, less the menu bar
	                   and the Dock, from NSScreen.visibleFrame. The desktop
	                   widget wants the whole frame instead, so that surface
	                   will ask for its own
	small_icon_size    the height of a menu bar item, fixed at 22 points rather
	                   than reported by the system. The Dock badge and the
	                   desktop widget are sized by their own surfaces
	animations_enabled the reduce motion preference, from
	                   NSWorkspace.accessibilityDisplayShouldReduceMotion
	apply_panel_chrome the vibrancy and corner radius of an NSPanel, which the
	                   window manager gives rather than the window asking. The
	                   desktop widget sits at the desktop window level instead
	claim_single_instance  a lock file under the application support directory,
	                   there being no named mutex
	set_startup_entry  a launch agent property list under ~/Library/LaunchAgents
	enable_dpi_awareness  nothing: macOS has always scaled by the display
"""

from __future__ import annotations

from ..validation import require_non_empty_str, require_positive_int, require_type

# Height of a menu bar item, in points. Fixed by the system rather than reported
# by it, unlike the notification area icon on Windows.
MENU_BAR_ICON_SIZE = 22


def enable_dpi_awareness() -> None:
	"""Ask the system to scale this process by the display.

	Returns:
		None. Nothing to do: macOS has always drawn at the scale of the display.
	"""


def claim_single_instance(name: str) -> bool:
	"""Claim a name for this process, and report whether it was free.

	Args:
		name: The name to claim, unique to what may run only once. str, non-empty.

	Returns:
		bool: True, since nothing is claimed yet. A machine that cannot answer
		should not be stopped from running the widget.
	"""
	require_non_empty_str(name, "name")
	return True


def small_icon_size() -> int:
	"""Return the edge length the system draws a menu bar icon at.

	Returns:
		int: The size in points.
	"""
	return MENU_BAR_ICON_SIZE


def work_area(fallback_width: int, fallback_height: int) -> tuple[int, int, int, int]:
	"""Return the screen rectangle that is not covered by the menu bar or Dock.

	Args:
		fallback_width: Screen width to report when the frame cannot be read, in
			pixels. int, greater than 0.
		fallback_height: Screen height to report when the frame cannot be read,
			in pixels. int, greater than 0.

	Returns:
		tuple[int, int, int, int]: The area as (left, top, right, bottom) in
		screen pixels, which for now is the whole screen.
	"""
	require_positive_int(fallback_width, "fallback_width")
	require_positive_int(fallback_height, "fallback_height")
	return (0, 0, fallback_width, fallback_height)


def animations_enabled() -> bool:
	"""Return whether the user allows interface animation.

	Returns:
		bool: True, which is what the Windows backend returns when the setting
		cannot be read.
	"""
	return True


def apply_panel_chrome(window_handle: int) -> None:
	"""Give a window rounded corners and the dark window manager treatment.

	Args:
		window_handle: The native window handle of the panel. int.

	Returns:
		None. The panel keeps the plain window it was given.
	"""
	require_type(window_handle, int, "window_handle")


def set_startup_entry(provider_key: str, enabled: bool) -> bool:
	"""Add or remove the entry that starts one provider's widget at login.

	Args:
		provider_key: Key of the provider, such as "claude". str, non-empty.
		enabled: True to add the entry, False to remove it. bool.

	Returns:
		bool: False, since nothing is registered yet, which is what the switch
		reports when the system refuses.
	"""
	require_non_empty_str(provider_key, "provider_key")
	require_type(enabled, bool, "enabled")
	return False
