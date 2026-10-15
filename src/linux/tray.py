"""The tray icons of the Linux widget, spoken over D-Bus.

Linux desktops show the icons of running programs through the
StatusNotifierItem protocol: a program puts an object on the session bus and
tells the StatusNotifierWatcher about it, and the panel of the desktop draws it.
KDE Plasma, Cinnamon, XFCE, MATE, Budgie, COSMIC, LXQt and status bars such as
Waybar host these icons themselves; GNOME hosts them through the AppIndicator
extension, which Ubuntu ships turned on.

The protocol is implemented here directly on the bus, with jeepney, which is
pure Python, rather than through a native library, so the single executable
needs nothing installed beside it.

One icon is put on the bus per usage the user chose to show, each on its own
connection under its own name, which every host tells apart. A left click opens
the panel. A right click shows a menu the desktop draws itself, through the
dbusmenu protocol, with the one item the menu of the Windows widget has: Quit.

Every icon has its own thread, which answers the desktop's questions about it,
while the widget changes what it shows from the interface thread; the
connection's own locks are what make sending from both safe.
"""

from __future__ import annotations

import os
import queue
import threading
from itertools import count
from typing import Any, Callable

from jeepney import DBusAddress, MatchRule, MessageType, new_error, new_method_call, new_method_return, new_signal
from jeepney.bus_messages import message_bus
from jeepney.io.threading import DBusRouter, open_dbus_connection
from jeepney.low_level import HeaderFields, Message
from PIL import Image

from src.common.ui.core import QUIT_LABEL, MetricReading
from src.common.validation import require_non_empty_str, require_type

WATCHER_NAME = "org.kde.StatusNotifierWatcher"
WATCHER = DBusAddress("/StatusNotifierWatcher", bus_name=WATCHER_NAME, interface=WATCHER_NAME)
ITEM_INTERFACE = "org.kde.StatusNotifierItem"
ITEM_PATH = "/StatusNotifierItem"
MENU_INTERFACE = "com.canonical.dbusmenu"
MENU_PATH = "/MenuBar"
PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
INTROSPECTABLE_INTERFACE = "org.freedesktop.DBus.Introspectable"
PEER_INTERFACE = "org.freedesktop.DBus.Peer"
UNKNOWN_METHOD = "org.freedesktop.DBus.Error.UnknownMethod"
UNKNOWN_PROPERTY = "org.freedesktop.DBus.Error.UnknownProperty"

# The sizes each icon is drawn at. A host picks the one closest to the size it
# shows icons at, so a range covers small panels, large ones and scaled displays.
ICON_SIZES = (16, 22, 24, 32, 48, 64)

# The single item of the right click menu, and the root that holds it.
MENU_ROOT_ID = 0
QUIT_ITEM_ID = 1
MENU_VERSION = 3

# How long to wait for the bus to answer a registration, in seconds.
CALL_TIMEOUT = 5.0

_NAME_SERIAL = count(1)

ITEM_XML = """<!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
"http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
<node>
	<interface name="org.kde.StatusNotifierItem">
		<property name="Category" type="s" access="read"/>
		<property name="Id" type="s" access="read"/>
		<property name="Title" type="s" access="read"/>
		<property name="Status" type="s" access="read"/>
		<property name="WindowId" type="i" access="read"/>
		<property name="IconName" type="s" access="read"/>
		<property name="IconPixmap" type="a(iiay)" access="read"/>
		<property name="OverlayIconName" type="s" access="read"/>
		<property name="OverlayIconPixmap" type="a(iiay)" access="read"/>
		<property name="AttentionIconName" type="s" access="read"/>
		<property name="AttentionIconPixmap" type="a(iiay)" access="read"/>
		<property name="AttentionMovieName" type="s" access="read"/>
		<property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
		<property name="ItemIsMenu" type="b" access="read"/>
		<property name="Menu" type="o" access="read"/>
		<property name="IconThemePath" type="s" access="read"/>
		<method name="ContextMenu"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
		<method name="Activate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
		<method name="SecondaryActivate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
		<method name="Scroll"><arg name="delta" type="i" direction="in"/><arg name="orientation" type="s" direction="in"/></method>
		<signal name="NewTitle"/>
		<signal name="NewIcon"/>
		<signal name="NewAttentionIcon"/>
		<signal name="NewOverlayIcon"/>
		<signal name="NewToolTip"/>
		<signal name="NewStatus"><arg name="status" type="s"/></signal>
	</interface>
	<interface name="org.freedesktop.DBus.Properties">
		<method name="Get"><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/></method>
		<method name="GetAll"><arg type="s" direction="in"/><arg type="a{sv}" direction="out"/></method>
	</interface>
</node>
"""

MENU_XML = """<!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
"http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
<node>
	<interface name="com.canonical.dbusmenu">
		<property name="Version" type="u" access="read"/>
		<property name="TextDirection" type="s" access="read"/>
		<property name="Status" type="s" access="read"/>
		<property name="IconThemePath" type="as" access="read"/>
		<method name="GetLayout"><arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="as" direction="in"/><arg type="u" direction="out"/><arg type="(ia{sv}av)" direction="out"/></method>
		<method name="GetGroupProperties"><arg type="ai" direction="in"/><arg type="as" direction="in"/><arg type="a(ia{sv})" direction="out"/></method>
		<method name="GetProperty"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/></method>
		<method name="Event"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="in"/><arg type="u" direction="in"/></method>
		<method name="EventGroup"><arg type="a(isvu)" direction="in"/><arg type="ai" direction="out"/></method>
		<method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
		<method name="AboutToShowGroup"><arg type="ai" direction="in"/><arg type="ai" direction="out"/><arg type="ai" direction="out"/></method>
		<signal name="ItemsPropertiesUpdated"><arg type="a(ia{sv})"/><arg type="a(ias)"/></signal>
		<signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
	</interface>
</node>
"""


def watcher_present() -> bool:
	"""Return whether this session has a StatusNotifierWatcher to show icons.

	Returns:
		bool: True when a host is running. False when there is none, as on GNOME
		without the AppIndicator extension, or when there is no session bus.
	"""
	try:
		connection = open_dbus_connection("SESSION")
	except (OSError, KeyError, ValueError, RuntimeError):
		return False
	try:
		with DBusRouter(connection) as router:
			reply = router.send_and_get_reply(message_bus.NameHasOwner(WATCHER_NAME), timeout=CALL_TIMEOUT)
			return bool(reply.body and reply.body[0])
	except (OSError, TimeoutError, RuntimeError, ValueError):
		return False
	finally:
		connection.close()


def _argb(image: Image.Image) -> bytes:
	"""Return an image's pixels in the order the protocol carries them.

	Args:
		image: The icon. PIL.Image.Image.

	Returns:
		bytes: Alpha, red, green and blue for each pixel, row by row, which is
		the 32 bit ARGB in network byte order the protocol asks for.
	"""
	red, green, blue, alpha = image.convert("RGBA").split()
	return Image.merge("RGBA", (alpha, red, green, blue)).tobytes()


def _variant(signature: str, value: Any) -> tuple[str, Any]:
	"""Return a value wrapped as a D-Bus variant.

	Args:
		signature: The D-Bus signature of the value, such as "s". str.
		value: The value. Any.

	Returns:
		tuple: The pair jeepney serialises as a variant.
	"""
	return (signature, value)


class _StatusItem:
	"""One icon on the bus: its properties, its menu, and the thread that answers for it."""

	def __init__(self, item_id: str, on_activate: Callable[[], None], on_quit: Callable[[], None]) -> None:
		"""Describe the icon without putting it on the bus yet.

		Args:
			item_id: Stable identifier the desktop remembers the icon's place and
				visibility by. str, non-empty.
			on_activate: Called on a left or middle click. Callable taking no
				arguments and returning None.
			on_quit: Called when Quit is chosen from the menu. Callable taking no
				arguments and returning None.

		Returns:
			None.
		"""
		require_non_empty_str(item_id, "item_id")
		self._id = item_id
		self._on_activate = on_activate
		self._on_quit = on_quit
		self._pixmaps: list[tuple[int, int, bytes]] = []
		self._tooltip = "FORL"
		self._name = f"org.kde.StatusNotifierItem-{os.getpid()}-{next(_NAME_SERIAL)}"
		self._connection: Any = None
		self._router: DBusRouter | None = None
		self._calls: queue.Queue[Message] = queue.Queue()
		self._watcher_changes: queue.Queue[Message] = queue.Queue()
		self._filters: list[Any] = []
		self._thread: threading.Thread | None = None
		self._closed = threading.Event()

	def _properties(self) -> dict[str, tuple[str, Any]]:
		"""Return every property of the icon, as variants.

		Returns:
			dict: The StatusNotifierItem properties by name.
		"""
		return {
			"Category": _variant("s", "ApplicationStatus"),
			"Id": _variant("s", self._id),
			"Title": _variant("s", "FORL"),
			"Status": _variant("s", "Active"),
			"WindowId": _variant("i", 0),
			"IconName": _variant("s", ""),
			"IconPixmap": _variant("a(iiay)", self._pixmaps),
			"OverlayIconName": _variant("s", ""),
			"OverlayIconPixmap": _variant("a(iiay)", []),
			"AttentionIconName": _variant("s", ""),
			"AttentionIconPixmap": _variant("a(iiay)", []),
			"AttentionMovieName": _variant("s", ""),
			"ToolTip": _variant("(sa(iiay)ss)", ("", [], self._tooltip, "")),
			"ItemIsMenu": _variant("b", False),
			"Menu": _variant("o", MENU_PATH),
			"IconThemePath": _variant("s", ""),
		}

	@staticmethod
	def _menu_properties() -> dict[str, tuple[str, Any]]:
		"""Return the properties of the menu object, as variants.

		Returns:
			dict: The dbusmenu properties by name.
		"""
		return {
			"Version": _variant("u", MENU_VERSION),
			"TextDirection": _variant("s", "ltr"),
			"Status": _variant("s", "normal"),
			"IconThemePath": _variant("as", []),
		}

	@staticmethod
	def _menu_items() -> dict[int, dict[str, tuple[str, Any]]]:
		"""Return every menu entry's properties, by id.

		Returns:
			dict: The root, which holds the entries, and the Quit entry.
		"""
		return {
			MENU_ROOT_ID: {"children-display": _variant("s", "submenu")},
			QUIT_ITEM_ID: {
				"label": _variant("s", QUIT_LABEL),
				"enabled": _variant("b", True),
				"visible": _variant("b", True),
			},
		}

	def _layout(self) -> tuple[int, dict[str, Any], list[Any]]:
		"""Return the menu tree in the shape GetLayout answers with.

		Returns:
			tuple: The root's id, properties and children, each child a variant
			holding the same shape.
		"""
		items = self._menu_items()
		quit_item = _variant("(ia{sv}av)", (QUIT_ITEM_ID, items[QUIT_ITEM_ID], []))
		return (MENU_ROOT_ID, items[MENU_ROOT_ID], [quit_item])

	def open(self) -> bool:
		"""Put the icon on the bus and tell the watcher about it.

		Returns:
			bool: True when the icon is on the bus. False when the bus or the
			watcher refused it, which leaves the widget running without it.
		"""
		try:
			self._connection = open_dbus_connection("SESSION")
			self._router = DBusRouter(self._connection)
			self._filters.append(self._router.filter(MatchRule(type=MessageType.method_call), queue=self._calls))
			# The watcher is a part of the desktop's panel, which restarts with it;
			# the icon is registered again with the new one when that happens.
			changes = MatchRule(
				type="signal",
				sender="org.freedesktop.DBus",
				interface="org.freedesktop.DBus",
				member="NameOwnerChanged",
			)
			changes.add_arg_condition(0, WATCHER_NAME)
			self._filters.append(self._router.filter(changes, queue=self._watcher_changes))
			self._router.send_and_get_reply(message_bus.AddMatch(changes), timeout=CALL_TIMEOUT)
			self._router.send_and_get_reply(message_bus.RequestName(self._name), timeout=CALL_TIMEOUT)
			self._thread = threading.Thread(target=self._serve, name=f"forl-tray-{self._id}", daemon=True)
			self._thread.start()
			self._register()
		except (OSError, TimeoutError, RuntimeError, ValueError, KeyError):
			self.close()
			return False
		return True

	def _register(self) -> None:
		"""Tell the watcher this icon exists.

		Returns:
			None.
		"""
		if self._router is None:
			return
		self._router.send_and_get_reply(
			new_method_call(WATCHER, "RegisterStatusNotifierItem", "s", (self._name,)),
			timeout=CALL_TIMEOUT,
		)

	def update(self, pixmaps: list[tuple[int, int, bytes]], tooltip: str) -> None:
		"""Change what the icon shows, and tell the desktop it changed.

		Args:
			pixmaps: The icon at every size, as (width, height, ARGB bytes). list.
			tooltip: The hover text. str.

		Returns:
			None.
		"""
		require_type(pixmaps, list, "pixmaps")
		require_type(tooltip, str, "tooltip")
		icon_changed = pixmaps != self._pixmaps
		tooltip_changed = tooltip != self._tooltip
		self._pixmaps = pixmaps
		self._tooltip = tooltip
		emitter = DBusAddress(ITEM_PATH, interface=ITEM_INTERFACE)
		try:
			if icon_changed and self._router is not None:
				self._router.send(new_signal(emitter, "NewIcon"))
			if tooltip_changed and self._router is not None:
				self._router.send(new_signal(emitter, "NewToolTip"))
		except OSError:
			pass

	def close(self) -> None:
		"""Take the icon off the bus.

		Returns:
			None.
		"""
		self._closed.set()
		for handle in self._filters:
			try:
				handle.close()
			except (OSError, RuntimeError, ValueError):
				pass
		self._filters.clear()
		if self._router is not None:
			try:
				self._router.close()
			except (OSError, RuntimeError):
				pass
			self._router = None
		if self._connection is not None:
			try:
				self._connection.close()
			except OSError:
				pass
			self._connection = None

	def _serve(self) -> None:
		"""Answer the desktop's calls until the icon is closed.

		Returns:
			None. Runs on the icon's own thread.
		"""
		while not self._closed.is_set():
			try:
				message = self._calls.get(timeout=0.5)
			except queue.Empty:
				self._follow_watcher()
				continue
			try:
				reply = self._answer(message)
			except Exception as exc:
				reply = new_error(message, "org.freedesktop.DBus.Error.Failed", "s", (str(exc),))
			if reply is not None and self._router is not None:
				try:
					self._router.send(reply)
				except OSError:
					return

	def _follow_watcher(self) -> None:
		"""Register again with a watcher that has just started.

		Returns:
			None.
		"""
		try:
			change = self._watcher_changes.get_nowait()
		except queue.Empty:
			return
		new_owner = change.body[2] if len(change.body) > 2 else ""
		if new_owner:
			try:
				self._register()
			except (OSError, TimeoutError, RuntimeError, ValueError):
				pass

	def _answer(self, message: Message) -> Message | None:
		"""Return the reply to one call, after doing what it asks.

		Args:
			message: The call. jeepney.low_level.Message.

		Returns:
			Message or None: The reply.
		"""
		fields = message.header.fields
		path = fields.get(HeaderFields.path, "")
		interface = fields.get(HeaderFields.interface, "")
		member = fields.get(HeaderFields.member, "")
		body = message.body

		if interface == PEER_INTERFACE:
			if member == "GetMachineId":
				return new_method_return(message, "s", ("",))
			return new_method_return(message)
		if interface == INTROSPECTABLE_INTERFACE or member == "Introspect":
			xml = MENU_XML if path == MENU_PATH else ITEM_XML
			return new_method_return(message, "s", (xml,))
		if interface == PROPERTIES_INTERFACE:
			properties = self._menu_properties() if path == MENU_PATH else self._properties()
			if member == "GetAll":
				return new_method_return(message, "a{sv}", (properties,))
			if member == "Get":
				name = body[1] if len(body) > 1 else ""
				if name not in properties:
					return new_error(message, UNKNOWN_PROPERTY, "s", (name,))
				return new_method_return(message, "v", (properties[name],))
			return new_error(message, UNKNOWN_METHOD, "s", (member,))
		if path == MENU_PATH:
			return self._answer_menu(message, member, body)
		if member in ("Activate", "SecondaryActivate"):
			self._on_activate()
			return new_method_return(message)
		if member in ("ContextMenu", "Scroll"):
			return new_method_return(message)
		return new_error(message, UNKNOWN_METHOD, "s", (member,))

	def _answer_menu(self, message: Message, member: str, body: tuple[Any, ...]) -> Message:
		"""Return the reply to one call on the menu.

		Args:
			message: The call. jeepney.low_level.Message.
			member: The method called. str.
			body: Its arguments. tuple.

		Returns:
			Message: The reply.
		"""
		items = self._menu_items()
		if member == "GetLayout":
			return new_method_return(message, "u(ia{sv}av)", (1, self._layout()))
		if member == "GetGroupProperties":
			ids = list(body[0]) if body and body[0] else list(items)
			return new_method_return(message, "a(ia{sv})", ([(item, items[item]) for item in ids if item in items],))
		if member == "GetProperty":
			item, name = body[0], body[1]
			value = items.get(item, {}).get(name, _variant("s", ""))
			return new_method_return(message, "v", (value,))
		if member == "Event":
			if body and body[0] == QUIT_ITEM_ID and body[1] == "clicked":
				self._on_quit()
			return new_method_return(message)
		if member == "EventGroup":
			for event in body[0] if body else []:
				if event[0] == QUIT_ITEM_ID and event[1] == "clicked":
					self._on_quit()
			return new_method_return(message, "ai", ([],))
		if member == "AboutToShow":
			return new_method_return(message, "b", (False,))
		if member == "AboutToShowGroup":
			return new_method_return(message, "aiai", ([], []))
		return new_error(message, UNKNOWN_METHOD, "s", (member,))


class TrayIcons:
	"""A set of tray icons, one per displayed usage, with the interface of the Windows one."""

	def __init__(
		self,
		name: str,
		draw: Callable[[float | None, int], Image.Image],
		on_activate: Callable[[], None],
		on_quit: Callable[[], None],
	) -> None:
		"""Create the manager with no icons showing yet.

		Args:
			name: Prefix of every icon's identifier, such as a provider key. The
				identifier is what the desktop remembers an icon's place by, so it
				must not change between runs. str, non-empty.
			draw: Returns the image of one icon, given its reading, or None
				before one has arrived, and its edge length in pixels. Callable
				taking a float or None and an int and returning a
				PIL.Image.Image.
			on_activate: Called on a left click, to open the panel. Callable
				taking no arguments and returning None.
			on_quit: Called when Quit is chosen from an icon's menu. Callable
				taking no arguments and returning None.

		Returns:
			None.
		"""
		require_non_empty_str(name, "name")
		for argument, callback in (("draw", draw), ("on_activate", on_activate), ("on_quit", on_quit)):
			if not callable(callback):
				raise TypeError(f"{argument} must be callable")
		self._name = name
		self._draw = draw
		self._on_activate = on_activate
		self._on_quit = on_quit
		self._items: dict[str, _StatusItem] = {}
		self._wanted: tuple[MetricReading, ...] = ()
		self._started = False

	def _pixmaps(self, percent: float | None) -> list[tuple[int, int, bytes]]:
		"""Return one reading drawn at every size a host may ask for.

		Args:
			percent: The reading, or None before one. float or None.

		Returns:
			list: (width, height, ARGB bytes) for each size.
		"""
		return [(size, size, _argb(self._draw(percent, size))) for size in ICON_SIZES]

	def start(self) -> None:
		"""Show the icons wanted so far.

		Returns:
			None.
		"""
		self._started = True
		self.sync(self._wanted)

	def sync(self, readings: tuple[MetricReading, ...]) -> None:
		"""Show one icon per reading, adding, updating and removing icons to match.

		Args:
			readings: The readings to show, in order. tuple of MetricReading.

		Returns:
			None.
		"""
		require_type(readings, tuple, "readings")
		self._wanted = readings
		if not self._started:
			return
		wanted_keys = {reading.key for reading in readings}
		for key in [key for key in self._items if key not in wanted_keys]:
			self._items.pop(key).close()
		for reading in readings:
			item = self._items.get(reading.key)
			if item is None:
				item = _StatusItem(f"forl-{self._name}-{reading.key}", self._on_activate, self._on_quit)
				# Drawn before it is put on the bus, so the desktop never sees it
				# empty.
				item.update(self._pixmaps(reading.percent), reading.tooltip)
				if not item.open():
					continue
				self._items[reading.key] = item
			else:
				item.update(self._pixmaps(reading.percent), reading.tooltip)

	def stop(self) -> None:
		"""Take every icon off the bus.

		Returns:
			None.
		"""
		self._started = False
		for item in self._items.values():
			item.close()
		self._items.clear()
