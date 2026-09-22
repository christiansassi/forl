"""The preferences file, and the defaults used when there is none.

One file holds both providers, keyed by provider key, and one more section for
what belongs to the widget as a whole, which is whether it starts at sign-in.
Saving any section re-reads the file first and writes only that section, so a
section written since this process last looked is not put back to what it was.

Whether the widget starts at sign-in used to be kept per provider, because each
provider ran in a process of its own. A file written then has no general
section; its answer is taken from the provider sections instead, and is on when
either of them was.

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
from ..schedule.session_start import SessionStart, from_dict as schedule_from_dict, to_dict as schedule_to_dict
from ..validation import require_non_empty_str, require_type

SETTINGS_FILE = "settings.json"

GENERAL_SECTION = "general"

STARTUP_FIELD = "start_on_startup"
VIEWS_FIELD = "views"
MENU_BAR_FIELD = "menu_bar"
DOCK_FIELD = "dock"
SESSION_START_FIELD = "session_start"

# On by default, so a widget that has never been configured is there after a
# restart rather than having to be started by hand.
DEFAULT_START_ON_STARTUP = True

# Both fields are only kept so an older preferences file survives a round trip.
DEFAULT_MENU_BAR = True
DEFAULT_DOCK = True



@dataclass(frozen=True)
class Preferences:
	"""What the widget remembers about one provider between runs.

	Attributes:
		views: Keys of the usages shown in the notification area or the menu bar,
			in the order the icons should appear. Empty means the user chose to
			show none. None means nothing was ever chosen, and the widget falls
			back to its own default. tuple of str, or None.
		menu_bar: Kept for a preferences file an older widget wrote. bool.
		dock: Kept for a preferences file an older widget wrote. bool.
		session_start: When to start the five hour session by sending a
			message, and the day it last did. SessionStart.
	"""

	views: tuple[str, ...] | None
	menu_bar: bool = DEFAULT_MENU_BAR
	dock: bool = DEFAULT_DOCK
	session_start: SessionStart = SessionStart()


DEFAULTS = Preferences(views=None)


def settings_path() -> Path:
	"""Return the file the preferences of every provider are kept in.

	Placed in the per user application data directory, which is where a setting
	that belongs to one signed-in user rather than to the machine belongs.

	Returns:
		Path: The path of the preferences file, whose parent may not exist yet.
	"""
	return data_file(SETTINGS_FILE)


def _section(name: str) -> dict[str, Any]:
	"""Return one stored section, as a plain dictionary.

	Args:
		name: Key of the section, a provider key such as "claude" or
			GENERAL_SECTION. str, non-empty.

	Returns:
		dict: The section, empty when the file or the section is missing.
	"""
	document = read_json(settings_path()) or {}
	section = document.get(name)
	return section if isinstance(section, dict) else {}


def _write_section(name: str, section: dict[str, Any]) -> bool:
	"""Replace one section of the file, leaving every other section as it is.

	Args:
		name: Key of the section. str, non-empty.
		section: The values to store under it. dict.

	Returns:
		bool: True when the file was written. False when it could not be, which
		costs the user the choice at the next launch and nothing more.
	"""
	require_non_empty_str(name, "name")
	require_type(section, dict, "section")

	path = settings_path()
	document = read_json(path) or {}
	document[name] = section
	try:
		path.parent.mkdir(parents=True, exist_ok=True)
		write_json(path, document)
	except OSError:
		return False
	return True


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
		views=tuple(view for view in views if isinstance(view, str) and view) if isinstance(views, list) else None,
		menu_bar=_flag(section, MENU_BAR_FIELD, DEFAULTS.menu_bar),
		dock=_flag(section, DOCK_FIELD, DEFAULTS.dock),
		session_start=schedule_from_dict(section.get(SESSION_START_FIELD)),
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
	section: dict[str, Any] = {
		MENU_BAR_FIELD: preferences.menu_bar,
		DOCK_FIELD: preferences.dock,
		SESSION_START_FIELD: schedule_to_dict(preferences.session_start),
	}
	if preferences.views is not None:
		section[VIEWS_FIELD] = list(preferences.views)
	return _write_section(provider_key, section)


def load_start_on_startup() -> bool:
	"""Return whether the widget should start when the user signs in.

	Returns:
		bool: The stored choice. From a file written before the choice was one
		for the whole widget, True when any provider section had it on; with no
		stored answer at all, DEFAULT_START_ON_STARTUP.
	"""
	general = _section(GENERAL_SECTION)
	if isinstance(general.get(STARTUP_FIELD), bool):
		return general[STARTUP_FIELD]

	document = read_json(settings_path()) or {}
	older = [
		section[STARTUP_FIELD]
		for name, section in document.items()
		if name != GENERAL_SECTION and isinstance(section, dict) and isinstance(section.get(STARTUP_FIELD), bool)
	]
	return any(older) if older else DEFAULT_START_ON_STARTUP


def save_start_on_startup(enabled: bool) -> bool:
	"""Store whether the widget should start when the user signs in.

	Args:
		enabled: The choice to store. bool.

	Returns:
		bool: True when the file was written, False when it could not be.
	"""
	require_type(enabled, bool, "enabled")
	section = _section(GENERAL_SECTION)
	section[STARTUP_FIELD] = enabled
	return _write_section(GENERAL_SECTION, section)
