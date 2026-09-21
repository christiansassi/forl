"""The notification area icons and the menu they share.

One icon is drawn per usage the user has chosen to display, so several readings
can sit side by side in the taskbar, each one a ring in the color of the service
it belongs to. Adding and removing icons is what a selection change means here:
the manager compares the wanted set against the icons already running and
creates, updates or retires each one.

A manager is named and handed the function that draws its icons rather than a
provider, because one set of icons belongs to no provider at all: the single
icon kept up while nobody is signed in, which is the only way into the panel.

Each icon is identified to Windows by a GUID made from its name, so Windows
keeps it where the user put it from one run to the next. Windows ties such a
GUID to the path of the program that first used it and silently refuses it to
any other, which is what happens when the same icon has been shown by the
widget run from source and is then shown by the built executable. An icon whose
GUID is refused is shown under a second GUID made from its name and the path of
the running program instead, which no other program can have claimed.

Windows would draw the menu of an icon itself, in the system style. It is drawn
by the widget instead, so a right click is caught here and reported rather than
handed to the shell, and the only item left with the shell is a hidden one: it
is what a left click invokes and it is never drawn.
"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
from ctypes import wintypes
from typing import Any, Callable
from uuid import NAMESPACE_URL, uuid5

import pystray
from PIL import Image
from pystray._util import win32

from ..validation import require_non_empty_str, require_number_in_range, require_positive_int, require_type
from ..system import small_icon_size
from .core import MetricReading

ICON_SIZE = 0
TOOLTIP_LIMIT = 127
ACTIVATE_ITEM = "Open"


class _Icon(pystray.Icon):
	"""A persistent tray icon that reports right clicks to the widget."""

	def __init__(self, name: str, *args: Any, on_menu: Callable[[int, int], None], **kwargs: Any) -> None:
		"""Create the icon and remember who to tell about a right click.

		Args:
			name: Stable provider and metric identifier. str, non-empty.
			*args: Positional arguments passed through to pystray. Any.
			on_menu: Called with the pointer position when the icon is right
				clicked. Callable taking two ints and returning None.
			**kwargs: Keyword arguments passed through to pystray. Any.

		Returns:
			None.
		"""
		require_non_empty_str(name, "name")
		if not callable(on_menu):
			raise TypeError("on_menu must be callable")
		super().__init__(name, *args, **kwargs)
		self._on_menu = on_menu
		# Kept stable so Windows retains each metric's placement between runs.
		self._guid = _guid(f"io.forl/tray/{name}")
		# Used instead when Windows has tied the stable one to another program.
		self._own_guid = _guid(f"io.forl/tray/{name}@{os.path.normcase(sys.executable)}")

	def _notify(self, code: int, flags: int, guid: Any, **kwargs: Any) -> bool:
		"""Send one Shell notification call for this icon under a given GUID.

		pystray sends these itself but drops the answer, and the answer is the
		only sign that Windows refused the GUID, so the call is made here.

		Args:
			code: Shell notification operation, one of the NIM constants. int.
			flags: Bitmask describing the supplied notification fields. int.
			guid: The identity to send. NOTIFYICONDATAW.GUID.
			**kwargs: Further notification fields. Any.

		Returns:
			bool: True when Windows accepted the call.
		"""
		return bool(
			win32.Shell_NotifyIcon(
				code,
				win32.NOTIFYICONDATAW(
					cbSize=ctypes.sizeof(win32.NOTIFYICONDATAW),
					hWnd=self._hwnd,
					hID=id(self),
					uFlags=flags | win32.NIF_GUID,
					guidItem=guid,
					**kwargs,
				),
			)
		)

	def _message(self, code: int, flags: int, **kwargs: Any) -> None:
		"""Identify the same persistent icon in every Shell notification call.

		An icon Windows refuses to add under its stable GUID is added under the
		one made from the path of this program, and keeps that one from then on.
		When both are refused, which is what an add made before the taskbar is up
		looks like, the stable one is kept: the add is repeated once the taskbar
		appears, and giving up the stable GUID then would cost the icon its place.

		Args:
			code: Shell notification operation, one of the NIM constants. int.
			flags: Bitmask describing the supplied notification fields. int.
			**kwargs: Notification fields passed through to pystray. Any.

		Returns:
			None.
		"""
		if self._notify(code, flags, self._guid, **kwargs) or code != win32.NIM_ADD:
			return
		if self._guid is not self._own_guid and self._notify(code, flags, self._own_guid, **kwargs):
			self._guid = self._own_guid

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


def _guid(text: str) -> Any:
	"""Return the tray icon GUID made from a piece of text.

	Args:
		text: What identifies the icon. str, non-empty.

	Returns:
		NOTIFYICONDATAW.GUID: The GUID, the same for the same text on every run.
	"""
	require_non_empty_str(text, "text")
	return win32.NOTIFYICONDATAW.GUID.from_buffer_copy(uuid5(NAMESPACE_URL, text).bytes_le)


class TrayIcons:
	"""A set of notification area icons, one per displayed usage."""

	def __init__(
		self,
		name: str,
		draw: Callable[[float | None, int], Image.Image],
		on_activate: Callable[[], None],
		on_menu: Callable[[int, int], None],
		icon_size: int = ICON_SIZE,
	) -> None:
		"""Create the manager with no icons showing yet.

		Args:
			name: Prefix of every icon's name, such as a provider key. The name
				is what Windows remembers an icon's place in the notification
				area by, so it must not change between runs. str, non-empty.
			draw: Returns the image of one icon, given its reading, or None
				before one has arrived, and its edge length in pixels. Callable
				taking a float or None and an int and returning a
				PIL.Image.Image.
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
		require_non_empty_str(name, "name")
		callbacks = (
			("draw", draw),
			("on_activate", on_activate),
			("on_menu", on_menu),
		)
		for argument, callback in callbacks:
			if not callable(callback):
				raise TypeError(f"{argument} must be callable")
		self._icon_size = icon_size or small_icon_size()
		require_positive_int(self._icon_size, "icon_size")

		self._name = name
		self._draw = draw
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
			f"{self._name}-usage-{reading.key}",
			icon=self._draw(reading.percent, self._icon_size),
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
		thread = threading.Thread(target=icon.run, name=f"tray-{self._name}-{key}", daemon=True)
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
			icon.icon = self._draw(reading.percent, self._icon_size)
			icon.title = reading.tooltip[:TOOLTIP_LIMIT]

	def stop(self) -> None:
		"""Remove every icon and end every message loop.

		Returns:
			None.
		"""
		for key in list(self._icons):
			self._retire(key)
		self._started = False
