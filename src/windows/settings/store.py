"""The preferences file, and the defaults used when there is none.

One file holds both providers, keyed by provider key, so a machine running the
Claude widget and the ChatGPT widget at once keeps one document rather than two.
Each instance owns one section of it and never writes another's, which is why
saving re-reads the file first: the other widget may have written its own
section since this one last looked.

Nothing here raises for a file that cannot be read. A preferences file that is
missing, unreadable or malformed simply gives the defaults, because a widget
that refuses to start over a lost preference would be worse than one that
forgets a choice. The sign-ins are kept in a file of their own for exactly that
reason: losing a preference is worth nothing, and losing a sign-in is worth a
trip through the browser.

Two fields survive from a macOS widget this file once served, so a preferences
file written by it is still read rather than reset. They are written back
unchanged and nothing on Windows reads them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..jsonstore import read_json, write_json
from ..paths import data_file
from ..validation import require_non_empty_str, require_type

SETTINGS_FILE = "settings.json"

STARTUP_FIELD = "start_on_startup"
VIEWS_FIELD = "views"
MENU_BAR_FIELD = "menu_bar"
DOCK_FIELD = "dock"

# On by default, so a widget that has never been configured is there after a
# restart rather than having to be started by hand.
DEFAULT_START_ON_STARTUP = True

# Both fields are only kept so an older preferences file survives a round trip.
DEFAULT_MENU_BAR = True
DEFAULT_DOCK = True



@dataclass(frozen=True)
class Preferences:
	"""What one provider's widget remembers between runs.

	Attributes:
		start_on_startup: Whether the widget should be launched when the user
			signs in to the machine. bool.
		views: Keys of the usages shown in the notification area or the menu bar,
			in the order the icons should appear. Empty means the widget has no
			stored selection and should fall back to its own default. tuple of
			str.
		menu_bar: Kept for a preferences file an older widget wrote. bool.
		dock: Kept for a preferences file an older widget wrote. bool.
	"""

	start_on_startup: bool
	views: tuple[str, ...]
	menu_bar: bool = DEFAULT_MENU_BAR
	dock: bool = DEFAULT_DOCK



DEFAULTS = Preferences(start_on_startup=DEFAULT_START_ON_STARTUP, views=())


def settings_path() -> Path:
	"""Return the file the preferences of every provider are kept in.

	Placed in the per user application data directory, which is where a setting
	that belongs to one signed-in user rather than to the machine belongs.

	Returns:
		Path: The path of the preferences file, whose parent may not exist yet.
	"""
	return data_file(SETTINGS_FILE)


def _section(provider_key: str) -> dict[str, Any]:
	"""Return the stored section of one provider, as a plain dictionary.

	Args:
		provider_key: Key of the provider, such as "claude". str, non-empty.

	Returns:
		dict: The section, empty when the file or the section is missing.
	"""
	document = read_json(settings_path()) or {}
	section = document.get(provider_key)
	return section if isinstance(section, dict) else {}


def _flag(section: dict[str, Any], field: str, fallback: bool) -> bool:
	"""Return one stored switch, falling back when it is missing or unusable.

	Args:
		section: The stored section of one provider. dict.
		field: Name of the field to read. str, non-empty.
		fallback: What to report when the field is absent or not a boolean. bool.

	Returns:
		bool: The stored value, or the fallback.
	"""
	require_type(section, dict, "section")
	require_non_empty_str(field, "field")
	require_type(fallback, bool, "fallback")
	value = section.get(field)
	return value if isinstance(value, bool) else fallback


def load(provider_key: str) -> Preferences:
	"""Return the stored preferences of one provider.

	Every field is checked rather than trusted, because the file is editable by
	hand and a bad value should cost that one preference and not the launch.

	Args:
		provider_key: Key of the provider, such as "claude". str, non-empty.

	Returns:
		Preferences: What was stored, with the defaults standing in for anything
		missing or unusable.
	"""
	require_non_empty_str(provider_key, "provider_key")

	section = _section(provider_key)
	views = section.get(VIEWS_FIELD)
	return Preferences(
		start_on_startup=_flag(section, STARTUP_FIELD, DEFAULTS.start_on_startup),
		views=tuple(view for view in views if isinstance(view, str) and view) if isinstance(views, list) else (),
		menu_bar=_flag(section, MENU_BAR_FIELD, DEFAULTS.menu_bar),
		dock=_flag(section, DOCK_FIELD, DEFAULTS.dock),
	)


def save(provider_key: str, preferences: Preferences) -> bool:
	"""Store the preferences of one provider, leaving the other's section alone.

	Args:
		provider_key: Key of the provider, such as "claude". str, non-empty.
		preferences: The values to store. Preferences.

	Returns:
		bool: True when the file was written. False when it could not be, which
		costs the user the choice at the next launch and nothing more.
	"""
	require_non_empty_str(provider_key, "provider_key")
	require_type(preferences, Preferences, "preferences")

	path = settings_path()
	document = read_json(path) or {}
	document[provider_key] = {
		STARTUP_FIELD: preferences.start_on_startup,
		VIEWS_FIELD: list(preferences.views),
		MENU_BAR_FIELD: preferences.menu_bar,
		DOCK_FIELD: preferences.dock,
	}
	try:
		path.parent.mkdir(parents=True, exist_ok=True)
		write_json(path, document)
	except OSError:
		return False
	return True
