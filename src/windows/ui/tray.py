"""The notification area icons and the menu they share.

One icon is drawn per usage the user has chosen to display, so several readings
can sit side by side in the taskbar, each one a ring in the color of the service
it belongs to. Adding and removing icons is what a
selection change means here: the manager compares the wanted set against the
icons already running and creates, updates or retires each one.

Windows would draw the menu of an icon itself, in the system style. It is drawn
by the widget instead, so a right click is caught here and reported rather than
handed to the shell, and the only item left with the shell is a hidden one: it
is what a left click invokes and it is never drawn.
"""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from typing import Callable

import pystray
from pystray._util import win32

from ..providers import Provider
from ..render.icon import render_icon
from ..validation import require_number_in_range, require_positive_int, require_type
from ..system import small_icon_size
from .core import MetricReading

ICON_SIZE = 0
TOOLTIP_LIMIT = 127
ACTIVATE_ITEM = "Open"


class _Icon(pystray.Icon):
	"""A tray icon that reports its right click instead of opening a menu."""

	def __init__(self, *args, on_menu: Callable[[int, int], None], **kwargs) -> None:
		"""Create the icon and remember who to tell about a right click.

		Args:
			*args: Passed through to pystray.
			on_menu: Called with the pointer position when the icon is right
				clicked. Callable taking two ints and returning None.
			**kwargs: Passed through to pystray.

		Returns:
			None.
		"""
		super().__init__(*args, **kwargs)
		self._on_menu = on_menu

	def _on_notify(self, wparam: int, lparam: int) -> None:
		"""Handle a mouse message on the icon.

		A right click is taken over so the widget can draw its own menu; every
		other message is left to pystray, which is what still makes a left click
		open the panel.

		Args:
			wparam: The message parameter pystray passes through. int.
			lparam: Which mouse message this is. int.

		Returns:
			None.
		"""
		if lparam == win32.WM_RBUTTONUP:
			point = wintypes.POINT()
			ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
			self._on_menu(point.x, point.y)
			return
		super()._on_notify(wparam, lparam)


class TrayIcons:
	"""A set of notification area icons, one per displayed usage."""

	def __init__(
		self,
		provider: Provider,
		on_activate: Callable[[], None],
		on_menu: Callable[[int, int], None],
		icon_size: int = ICON_SIZE,
	) -> None:
		"""Create the manager with no icons showing yet.

		Args:
			provider: The service being reported on. Its key prefixes every icon
				name, so two instances of the widget can run side by side, and its
				color is what the rings are drawn in. Provider.
			on_activate: Called on a left click, to open the panel. Callable
				taking no arguments and returning None.
			on_menu: Called with the pointer position when an icon is right
				clicked, so the widget can open its own menu there. Callable
				taking two ints and returning None.
			icon_size: Edge length in pixels of each rendered icon bitmap, or 0 to
				draw at the size the shell displays them. int, 0 or more.

		Returns:
			None.
		"""
		callbacks = (
			("on_activate", on_activate),
			("on_menu", on_menu),
		)
		for name, callback in callbacks:
			if not callable(callback):
				raise TypeError(f"{name} must be callable")
		self._icon_size = icon_size or small_icon_size()
		require_positive_int(self._icon_size, "icon_size")
		require_type(provider, Provider, "provider")

		self._provider = provider
		self._on_activate = on_activate
		self._on_menu = on_menu

		self._icons: dict[str, pystray.Icon] = {}
		self._threads: dict[str, threading.Thread] = {}
		self._started = False

	def _hidden_menu(self) -> pystray.Menu:
		"""Return the only menu the shell is given: one item, never drawn.

		pystray finds the default item among all of them but draws only the
		visible ones, so an invisible default leaves a left click working while
		giving the shell nothing to pop up.

		Returns:
			pystray.Menu: The menu to attach to every icon.
		"""
		return pystray.Menu(
			pystray.MenuItem(
				ACTIVATE_ITEM,
				lambda _icon, _item: self._on_activate(),
				default=True,
				visible=False,
			)
		)

	def _create_icon(self, reading: MetricReading) -> pystray.Icon:
		"""Create and show one icon for a usage.

		Args:
			reading: What the new icon should show. MetricReading.

		Returns:
			pystray.Icon: The icon, already running on its own thread when the
			manager has been started.
		"""
		icon = _Icon(
			f"{self._provider.key}-usage-{reading.key}",
			icon=render_icon(reading.percent, self._icon_size, self._provider.accent),
			title=reading.tooltip[:TOOLTIP_LIMIT],
			menu=self._hidden_menu(),
			on_menu=self._on_menu,
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
		thread = threading.Thread(target=icon.run, name=f"tray-{self._provider.key}-{key}", daemon=True)
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

	def sync(self, readings: tuple[MetricReading, ...]) -> None:
		"""Make the icons on screen match the readings, creating and retiring as needed.

		Args:
			readings: One entry per usage to display, in the order the icons
				should appear. tuple of MetricReading.

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
			icon.icon = render_icon(reading.percent, self._icon_size, self._provider.accent)
			icon.title = reading.tooltip[:TOOLTIP_LIMIT]

	def stop(self) -> None:
		"""Remove every icon and end every message loop.

		Returns:
			None.
		"""
		for key in list(self._icons):
			self._retire(key)
		self._started = False
