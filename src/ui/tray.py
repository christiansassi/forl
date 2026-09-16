"""The notification area icons and the menu they share.

One icon is drawn per usage the user has chosen to display, so several readings
can sit side by side in the taskbar. Adding and removing icons is what a
selection change means here: the manager compares the wanted set against the
icons already running and creates, updates or retires each one.

Every icon carries the same menu, which lists all available usages as check
items. The menu is generated at each opening rather than built once, because the
usages an account reports change between readings. Opening the panel is a hidden
default item: it is what a left click invokes, and it is not drawn in the menu.
"""

from __future__ import annotations

import threading
from typing import Callable, NamedTuple

import pystray

from ..render.icon import render_icon
from ..usage.snapshot import LIMIT_GROUP, PRODUCT_GROUP
from ..validation import require_non_empty_str, require_number_in_range, require_positive_int, require_type

ICON_SIZE = 64
TOOLTIP_LIMIT = 127


class MenuOption(NamedTuple):
	"""One usage offered in the menu.

	Attributes:
		key: Stable identifier of the usage. str.
		label: Name shown in the menu. str.
		group: Either "limit" or "product", which decides where the separator
			falls. str.
	"""

	key: str
	label: str
	group: str


class IconReading(NamedTuple):
	"""What one icon should currently show.

	Attributes:
		key: Stable identifier of the usage the icon stands for. str.
		percent: Share already used, 0 to 100, or None before the first reading
			has arrived. float or None.
		tooltip: Hover text for the icon. str.
	"""

	key: str
	percent: float | None
	tooltip: str


class TrayIcons:
	"""A set of notification area icons, one per displayed usage."""

	def __init__(
		self,
		provider_key: str,
		on_activate: Callable[[], None],
		on_toggle: Callable[[str], None],
		on_quit: Callable[[], None],
		icon_size: int = ICON_SIZE,
	) -> None:
		"""Create the manager with no icons showing yet.

		Args:
			provider_key: Key of the service being reported on, which prefixes
				every icon name so two instances of the widget can run side by
				side. str, non-empty.
			on_activate: Called on a left click, to open the panel. Callable
				taking no arguments and returning None.
			on_toggle: Called with the key of the usage whose check mark the user
				clicked. Callable taking one str and returning None.
			on_quit: Called when the user picks "Quit". Callable taking no
				arguments and returning None.
			icon_size: Edge length in pixels of each rendered icon bitmap. int,
				greater than 0.

		Returns:
			None.
		"""
		callbacks = (
			("on_activate", on_activate),
			("on_toggle", on_toggle),
			("on_quit", on_quit),
		)
		for name, callback in callbacks:
			if not callable(callback):
				raise TypeError(f"{name} must be callable")
		require_positive_int(icon_size, "icon_size")
		require_non_empty_str(provider_key, "provider_key")

		self._provider_key = provider_key
		self._on_activate = on_activate
		self._on_toggle = on_toggle
		self._on_quit = on_quit
		self._icon_size = icon_size

		self._icons: dict[str, pystray.Icon] = {}
		self._threads: dict[str, threading.Thread] = {}
		self._options: tuple[MenuOption, ...] = ()
		self._selected: frozenset[str] = frozenset()
		self._started = False

	def _menu_items(self):
		"""Yield the menu shown on a right click, rebuilt at every opening.

		Returns:
			Iterator of pystray.MenuItem: The hidden activation item, one check
			item per available usage, and the quit command.
		"""
		# Hidden, yet still the item a left click invokes: pystray looks for the
		# default among all items and draws only the visible ones.
		yield pystray.MenuItem(
			"Show all usage",
			lambda _icon, _item: self._on_activate(),
			default=True,
			visible=False,
		)
		for group in (LIMIT_GROUP, PRODUCT_GROUP):
			options = [option for option in self._options if option.group == group]
			if not options:
				continue
			for option in options:
				yield pystray.MenuItem(
					option.label,
					self._toggle_action(option.key),
					checked=self._checked_probe(option.key),
				)
			yield pystray.Menu.SEPARATOR
		yield pystray.MenuItem("Quit", lambda _icon, _item: self._on_quit())

	def _toggle_action(self, key: str) -> Callable[[object, object], None]:
		"""Return the menu action that shows or hides one usage.

		Args:
			key: Key of the usage the item stands for. str, non-empty.

		Returns:
			Callable: The action pystray calls when that item is clicked.
		"""
		require_non_empty_str(key, "key")
		return lambda _icon, _item: self._on_toggle(key)

	def _checked_probe(self, key: str) -> Callable[[object], bool]:
		"""Return the predicate that marks one usage as displayed.

		Args:
			key: Key of the usage the item stands for. str, non-empty.

		Returns:
			Callable: The predicate pystray calls to draw the check mark.
		"""
		require_non_empty_str(key, "key")
		return lambda _item: key in self._selected

	def _create_icon(self, reading: IconReading) -> pystray.Icon:
		"""Create and show one icon for a usage.

		Args:
			reading: What the new icon should show. IconReading.

		Returns:
			pystray.Icon: The icon, already running on its own thread when the
			manager has been started.
		"""
		icon = pystray.Icon(
			f"{self._provider_key}-usage-{reading.key}",
			icon=render_icon(reading.percent, self._icon_size),
			title=reading.tooltip[:TOOLTIP_LIMIT],
			menu=pystray.Menu(self._menu_items),
		)
		self._icons[reading.key] = icon
		if self._started:
			self._run(reading.key, icon)
		return icon

	def _run(self, key: str, icon: pystray.Icon) -> None:
		"""Start one icon message loop on its own thread.

		Args:
			key: Key of the usage the icon stands for. str.
			icon: The icon to run. pystray.Icon.

		Returns:
			None.
		"""
		thread = threading.Thread(target=icon.run, name=f"tray-{self._provider_key}-{key}", daemon=True)
		self._threads[key] = thread
		thread.start()

	def _retire(self, key: str) -> None:
		"""Remove one icon from the notification area and end its message loop.

		Args:
			key: Key of the usage whose icon should go. str.

		Returns:
			None.
		"""
		icon = self._icons.pop(key, None)
		self._threads.pop(key, None)
		if icon is not None:
			icon.visible = False
			icon.stop()

	def start(self) -> None:
		"""Run the message loop of every icon created so far.

		Returns:
			None. Calling it on a started manager does nothing.
		"""
		if self._started:
			return
		self._started = True
		for key, icon in self._icons.items():
			self._run(key, icon)

	def set_menu(self, options: tuple[MenuOption, ...], selected: frozenset[str]) -> None:
		"""Replace what the menu offers and how it is marked.

		Args:
			options: Every usage the account currently reports, in menu order.
				tuple of MenuOption.
			selected: Keys of the usages being displayed. frozenset of str.

		Returns:
			None.
		"""
		require_type(options, tuple, "options")
		require_type(selected, frozenset, "selected")

		changed = (options, selected) != (self._options, self._selected)
		self._options = options
		self._selected = selected
		if changed:
			for icon in self._icons.values():
				icon.update_menu()

	def sync(self, readings: tuple[IconReading, ...]) -> None:
		"""Make the icons on screen match the readings, creating and retiring as needed.

		Args:
			readings: One entry per usage to display, in the order the icons
				should appear. tuple of IconReading.

		Returns:
			None.
		"""
		require_type(readings, tuple, "readings")

		wanted = {reading.key for reading in readings}
		for key in [key for key in self._icons if key not in wanted]:
			self._retire(key)

		for reading in readings:
			if reading.percent is not None:
				require_number_in_range(reading.percent, 0.0, 100.0, "reading.percent")
			icon = self._icons.get(reading.key)
			if icon is None:
				self._create_icon(reading)
				continue
			icon.icon = render_icon(reading.percent, self._icon_size)
			icon.title = reading.tooltip[:TOOLTIP_LIMIT]

	def stop(self) -> None:
		"""Remove every icon and end every message loop.

		Returns:
			None.
		"""
		for key in list(self._icons):
			self._retire(key)
		self._started = False
