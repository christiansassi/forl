"""Everything this widget asks of a Linux desktop.

Linux has many desktops and they agree on less than Windows does, so every
answer here is asked of the shared standards first, the XDG desktop portal, the
XDG base directories, freedesktop autostart and fontconfig, then of GNOME's and
KDE's own settings, and degrades to a sensible default when none of them says.
A question nobody can answer costs a detail, never the launch.

This is the Linux backend behind the names of src/common/system, which the
Linux entry point installs before anything else runs. The shared code never
imports it directly.
"""

from __future__ import annotations

import configparser
import os
import shlex
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from src.common.system import EDGE_BOTTOM, EDGE_TOP
from src.common.validation import require_member, require_non_empty_str, require_positive_int, require_type

APP_DIR_NAME = "forl"

# The KDE Plasma widget, as it ships beside this module and inside the built
# executable, and where Plasma looks for widgets a user installed.
PLASMA_WIDGET_ID = "io.forl.usage"
PLASMA_WIDGET_SOURCE = Path(__file__).resolve().parent / "plasma" / PLASMA_WIDGET_ID
PLASMA_WIDGETS_DIR = ("plasma", "plasmoids")
AUTOSTART_FILE = "forl.desktop"
ENTRY_SCRIPT = Path(__file__).resolve().parent / "main.py"

# How long a helper program may take to answer, in seconds. Each one is a
# preference lookup that normally answers at once.
HELPER_TIMEOUT = 2.0

# Desktops whose panel, and so whose tray, is at the top of the screen by
# default. The others put theirs at the bottom, as Windows does.
TOP_BAR_DESKTOPS = ("GNOME", "UNITY", "PANTHEON", "COSMIC", "XFCE", "MATE", "BUDGIE", "HYPRLAND", "SWAY")

# Room left for a top bar when the work area cannot be read, as on Wayland,
# where X11 programs are not told about the desktop's panels.
TOP_BAR_ALLOWANCE = 40

# The faces type is drawn into images with when fontconfig cannot be asked,
# best first. Every major distribution ships at least one of these families.
FALLBACK_FONT_FILES = {
	"bold": (
		"/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
		"/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
		"/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
		"/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
		"/usr/share/fonts/noto/NotoSans-Bold.ttf",
		"/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
	),
	"normal": (
		"/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
		"/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
		"/usr/share/fonts/TTF/DejaVuSans.ttf",
		"/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
		"/usr/share/fonts/noto/NotoSans-Regular.ttf",
		"/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
	),
}
FALLBACK_FONT_FAMILY = "DejaVu Sans"

# The color scheme values the XDG desktop portal reports.
PORTAL_PREFERS_DARK = 1
PORTAL_PREFERS_LIGHT = 2

# Held for as long as the process runs: the lock that keeps a second copy out
# is released when the file is closed, which the system does when it ends.
_LOCK_FILES: list[Any] = []


def _run(command: list[str]) -> str:
	"""Return what a helper program prints, or nothing when it cannot be run.

	Args:
		command: The program and its arguments. list of str, non-empty.

	Returns:
		str: Its standard output, stripped, or an empty string when the program
		is missing, fails or takes too long.
	"""
	require_type(command, list, "command")
	if not command or shutil.which(command[0]) is None:
		return ""
	try:
		result = subprocess.run(command, capture_output=True, text=True, timeout=HELPER_TIMEOUT, check=False)
	except (OSError, subprocess.SubprocessError):
		return ""
	return result.stdout.strip() if result.returncode == 0 else ""


def _xdg_dir(variable: str, *default: str) -> Path:
	"""Return an XDG base directory.

	Args:
		variable: The environment variable that names it, such as
			"XDG_CONFIG_HOME". str, non-empty.
		*default: The path under the home directory used when it is not set.
			str.

	Returns:
		Path: The directory, which may not exist yet.
	"""
	require_non_empty_str(variable, "variable")
	value = os.environ.get(variable)
	return Path(value) if value else Path.home().joinpath(*default)


def _desktops() -> list[str]:
	"""Return the names of the desktop this session runs, in capitals.

	Returns:
		list of str: The parts of XDG_CURRENT_DESKTOP, such as ["UBUNTU",
		"GNOME"], empty when it is not set.
	"""
	return [part.strip().upper() for part in os.environ.get("XDG_CURRENT_DESKTOP", "").split(":") if part.strip()]


def _kde_setting(section: str, key: str) -> str:
	"""Return one value of KDE's global settings.

	Args:
		section: The group, such as "General". str, non-empty.
		key: The key, such as "ColorScheme". str, non-empty.

	Returns:
		str: The value, or an empty string when KDE has not stored it.
	"""
	require_non_empty_str(section, "section")
	require_non_empty_str(key, "key")
	parser = configparser.ConfigParser(interpolation=None, strict=False)
	try:
		parser.read(_xdg_dir("XDG_CONFIG_HOME", ".config") / "kdeglobals", encoding="utf-8")
	except (OSError, configparser.Error):
		return ""
	return parser.get(section, key, fallback="")


def _portal_color_scheme() -> int | None:
	"""Return the color scheme the XDG desktop portal reports.

	Returns:
		int or None: 1 for dark, 2 for light, 0 for no preference, or None when
		there is no portal to ask.
	"""
	try:
		from jeepney import DBusAddress, new_method_call
		from jeepney.io.blocking import open_dbus_connection
	except ImportError:
		return None
	portal = DBusAddress(
		"/org/freedesktop/portal/desktop",
		bus_name="org.freedesktop.portal.Desktop",
		interface="org.freedesktop.portal.Settings",
	)
	try:
		with open_dbus_connection("SESSION") as connection:
			for method in ("ReadOne", "Read"):
				message = new_method_call(portal, method, "ss", ("org.freedesktop.appearance", "color-scheme"))
				try:
					reply = connection.send_and_get_reply(message, timeout=HELPER_TIMEOUT)
				except (OSError, TimeoutError):
					continue
				value: Any = reply.body[0] if reply.body else None
				# ReadOne answers with the value in a variant; the older Read wraps
				# that variant in another.
				while isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], str):
					value = value[1]
				if isinstance(value, int):
					return value
	except (OSError, ValueError, RuntimeError, KeyError):
		return None
	return None


def uses_light_theme() -> bool:
	"""Return whether the user has chosen the light mode for applications.

	Asked of the XDG desktop portal first, which GNOME, KDE, Cinnamon and COSMIC
	all answer, then of GNOME's and KDE's own settings.

	Returns:
		bool: True for the light mode, False for the dark mode, and True when
		nothing says, which is what every desktop starts in.
	"""
	scheme = _portal_color_scheme()
	if scheme == PORTAL_PREFERS_DARK:
		return False
	if scheme == PORTAL_PREFERS_LIGHT:
		return True
	gnome = _run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"])
	if "dark" in gnome:
		return False
	theme = _run(["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"])
	if "dark" in theme.lower():
		return False
	if "dark" in _kde_setting("General", "ColorScheme").lower():
		return False
	return True


def animations_enabled() -> bool:
	"""Return whether the user allows interface animation.

	Returns:
		bool: False when GNOME's animations are turned off or KDE's animation
		speed is set to instant, True otherwise.
	"""
	if _run(["gsettings", "get", "org.gnome.desktop.interface", "enable-animations"]) == "false":
		return False
	factor = _kde_setting("KDE", "AnimationDurationFactor")
	try:
		return not (factor and float(factor) == 0.0)
	except ValueError:
		return True


def apply_panel_chrome(window_handle: int, dark: bool) -> None:
	"""Give the panel the chrome of a mode.

	Args:
		window_handle: The native window handle of the panel. int.
		dark: Whether the panel is drawn in the dark mode. bool.

	Returns:
		None. Nothing to do: Linux window managers draw no chrome around a window
		that asks for none, which the panel does.
	"""
	require_type(window_handle, int, "window_handle")
	require_type(dark, bool, "dark")


def enable_dpi_awareness() -> None:
	"""Ask the system to scale this process by the display.

	Returns:
		None. Nothing to do: Tk reads the display's resolution from the X server
		and scales by it already.
	"""


def detach(name: str) -> None:
	"""Put this process into the background.

	Args:
		name: The name of this widget. str, non-empty.

	Returns:
		None. Nothing to do: the desktop starts the widget without a terminal,
		and one started from a terminal is meant to stay attached to it.
	"""
	require_non_empty_str(name, "name")


def claim_single_instance(name: str) -> bool:
	"""Claim a name for this process, and report whether it was free.

	Claimed with a lock on a file in the session's runtime directory, which the
	system releases when the process ends, so a widget that is killed or
	crashes does not keep the name locked.

	Args:
		name: The name to claim, unique to what may run only once. str, non-empty.

	Returns:
		bool: True when this process now holds the name, False when another
		process already did. True when no lock can be taken, since a machine
		that cannot answer should not be stopped from running the widget.
	"""
	require_non_empty_str(name, "name")
	import fcntl

	runtime = os.environ.get("XDG_RUNTIME_DIR") or str(_xdg_dir("XDG_CACHE_HOME", ".cache") / APP_DIR_NAME)
	try:
		Path(runtime).mkdir(parents=True, exist_ok=True)
		handle = open(Path(runtime) / f"forl-{name}.lock", "w")
	except OSError:
		return True
	try:
		fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
	except BlockingIOError:
		handle.close()
		return False
	except OSError:
		handle.close()
		return True
	_LOCK_FILES.append(handle)
	return True


def panel_edge() -> str:
	"""Return the edge of the screen the panel opens from.

	Returns:
		str: EDGE_TOP on desktops whose panel is at the top by default, such as
		GNOME, COSMIC and XFCE, and EDGE_BOTTOM on the others, such as KDE
		Plasma and Cinnamon.
	"""
	desktops = _desktops()
	if any(desktop in TOP_BAR_DESKTOPS for desktop in desktops):
		return EDGE_TOP
	return EDGE_BOTTOM if desktops else EDGE_TOP


def work_area(fallback_width: int, fallback_height: int) -> tuple[int, int, int, int]:
	"""Return the desktop rectangle not covered by a panel.

	Read from the window manager's _NET_WORKAREA, which X11 desktops publish.
	Where it cannot be read, room is left for a top bar on a desktop that has
	one.

	Args:
		fallback_width: Screen width in pixels. int, greater than 0.
		fallback_height: Screen height in pixels. int, greater than 0.

	Returns:
		tuple[int, int, int, int]: The work area as (left, top, right, bottom) in
		screen pixels.
	"""
	require_positive_int(fallback_width, "fallback_width")
	require_positive_int(fallback_height, "fallback_height")
	answer = _run(["xprop", "-root", "-notype", "_NET_WORKAREA"])
	if "=" in answer:
		try:
			left, top, width, height = (int(part) for part in answer.split("=", 1)[1].split(",")[:4])
		except ValueError:
			left = top = width = height = 0
		if width > 0 and height > 0:
			return (left, top, left + width, top + height)
	top = TOP_BAR_ALLOWANCE if panel_edge() == EDGE_TOP else 0
	return (0, top, fallback_width, fallback_height)


@lru_cache(maxsize=1)
def ui_font_family() -> str:
	"""Return the family the interface text is set in.

	Returns:
		str: The desktop's sans serif family as fontconfig names it, such as
		"Ubuntu Sans", "Cantarell" or "Noto Sans", or DejaVu Sans when
		fontconfig cannot be asked.
	"""
	family = _run(["fc-match", "--format=%{family[0]}", "sans-serif"])
	return family or FALLBACK_FONT_FAMILY


@lru_cache(maxsize=2)
def font_files(weight: str) -> tuple[str, ...]:
	"""Return the font files to try, in order, for type drawn into images.

	Args:
		weight: Either "normal" or "bold". str.

	Returns:
		tuple of str: The file fontconfig picks for the interface family at that
		weight, then the common fallbacks.
	"""
	require_member(weight, frozenset(FALLBACK_FONT_FILES), "weight")
	pattern = f"{ui_font_family()}:weight={'bold' if weight == 'bold' else 'regular'}"
	chosen = _run(["fc-match", "--format=%{file}", pattern])
	return ((chosen,) if chosen else ()) + FALLBACK_FONT_FILES[weight]


def _command() -> list[str]:
	"""Return the command that starts the widget.

	Returns:
		list of str: The executable itself when this is the built widget, and
		the interpreter with the entry script when it runs from source.
	"""
	if getattr(sys, "frozen", False):
		return [sys.executable]
	return [sys.executable, str(ENTRY_SCRIPT)]


def set_startup_entry(enabled: bool) -> bool:
	"""Add or remove the entry that starts the widget at sign-in.

	The entry is a desktop file in the XDG autostart directory, which every
	Linux desktop reads at sign-in and lists in its own startup settings, so the
	user can see and undo it from outside the widget.

	Args:
		enabled: True to write the entry, False to remove it. bool.

	Returns:
		bool: True when the directory now says what was asked, including when
		the entry was already absent and removal was asked for. False when it
		could not be written.
	"""
	require_type(enabled, bool, "enabled")
	entry = _xdg_dir("XDG_CONFIG_HOME", ".config") / "autostart" / AUTOSTART_FILE
	try:
		if not enabled:
			entry.unlink(missing_ok=True)
			return True
		entry.parent.mkdir(parents=True, exist_ok=True)
		entry.write_text(
			"[Desktop Entry]\n"
			"Type=Application\n"
			"Name=FORL\n"
			"Comment=Claude and ChatGPT usage limits\n"
			f"Exec={shlex.join(_command())}\n"
			"Terminal=false\n"
			"X-GNOME-Autostart-enabled=true\n",
			encoding="utf-8",
		)
	except OSError:
		return False
	return True


def _install_tree(source: Path, target: Path) -> bool:
	"""Copy a directory that ships with the widget to where a desktop reads it.

	Only the files that differ are written, so a copy that already matches is
	left alone and the desktop sees no change to pick up.

	Args:
		source: The directory as it ships, beside this module or inside the
			built executable. Path.
		target: Where the desktop looks for it, created when missing. Path.

	Returns:
		bool: True when the target now matches the source. False when the
		source is missing or a file could not be copied.
	"""
	require_type(source, Path, "source")
	require_type(target, Path, "target")
	if not source.is_dir():
		return False
	try:
		for path in source.rglob("*"):
			if not path.is_file():
				continue
			destination = target / path.relative_to(source)
			content = path.read_bytes()
			if destination.is_file() and destination.read_bytes() == content:
				continue
			destination.parent.mkdir(parents=True, exist_ok=True)
			destination.write_bytes(content)
	except OSError:
		return False
	return True


def install_plasma_widget() -> bool:
	"""Install the KDE Plasma widget for this user, or bring it up to date.

	Done at every launch on a Plasma desktop, by copying the widget into the
	directory Plasma lists installed widgets from, so it is in Add Widgets
	without the user installing anything. A copy that already matches is left
	alone.

	Returns:
		bool: True when the widget is installed and current. False on a desktop
		that is not Plasma, or when it could not be copied.
	"""
	if "KDE" not in _desktops():
		return False
	target = _xdg_dir("XDG_DATA_HOME", ".local", "share").joinpath(*PLASMA_WIDGETS_DIR) / PLASMA_WIDGET_ID
	return _install_tree(PLASMA_WIDGET_SOURCE, target)


def status_dir() -> Path | None:
	"""Return where the readings are written for status bars and desktop widgets.

	Returns:
		Path: $XDG_CACHE_HOME/forl, by default ~/.cache/forl.
	"""
	return _xdg_dir("XDG_CACHE_HOME", ".cache") / APP_DIR_NAME


def tray_available() -> bool:
	"""Return whether this session has a tray to put icons in.

	Returns:
		bool: True when a StatusNotifierWatcher is running, which every desktop
		with a tray provides and GNOME provides through the AppIndicator
		extension.
	"""
	from .tray import watcher_present

	return watcher_present()


def create_tray(
	name: str,
	draw: Callable[[float | None, int], Any],
	on_activate: Callable[[], None],
	on_menu: Callable[[int, int], None],
	on_quit: Callable[[], None],
) -> Any:
	"""Return a set of tray icons, none showing yet.

	Args:
		name: Prefix of every icon's identifier, such as a provider key. str,
			non-empty.
		draw: Returns the image of one icon, given its reading and its edge
			length. Callable taking a float or None and an int and returning a
			PIL.Image.Image.
		on_activate: Called on a left click. Callable taking no arguments and
			returning None.
		on_menu: Not called on Linux, where the desktop draws the menu itself.
			Callable taking two ints and returning None.
		on_quit: Called when Quit is chosen from that menu. Callable taking no
			arguments and returning None.

	Returns:
		TrayIcons: The icons of src/linux/tray.py.
	"""
	if not callable(on_menu):
		raise TypeError("on_menu must be callable")
	from .tray import TrayIcons

	return TrayIcons(name, draw, on_activate, on_quit)
