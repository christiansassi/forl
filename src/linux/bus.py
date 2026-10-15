"""The widget's readings and its panel, offered on the session bus.

The GNOME Shell extension under src/linux/gnome draws the readings in the top
bar, but it runs inside the Shell and FORL runs on its own, so the two meet on
the session bus, the way the Mac app and its widgets meet through WidgetKit:

	GetStatus() -> s        everything status.json holds, as the same JSON
	StatusChanged(s)        sent each time that changes, so nothing polls
	Open(s service, s view) open the panel on a service, on the reading or the
	                        settings, as a widget opens the Mac app

A desktop file for the bus names the executable, so a call to Open starts the
widget when it is not running, the way opening a forl:// address starts the Mac
app. status.json is still written for the Plasma widget and for status bars,
which can read only files.

The extension also puts a name of its own on the bus. While it holds the name
and there is no tray, the extension stands in for the tray: the panel opens
from the top bar when asked and hides when it loses focus, instead of being an
ordinary window that quits the widget when closed.

Calls are answered on a thread of the service's own, and the widget publishes
from its interface thread; the connection's own locks are what make sending
from both safe, as in tray.py.
"""

from __future__ import annotations

import json
import queue
import threading
from typing import Any, Callable

from jeepney import DBusAddress, MatchRule, MessageType, new_error, new_method_return, new_signal
from jeepney.bus_messages import message_bus
from jeepney.io.threading import DBusRouter, open_dbus_connection
from jeepney.low_level import HeaderFields, Message

from src.common.validation import require_type

BUS_NAME = "io.forl.Usage"
OBJECT_PATH = "/io/forl/Usage"
INTERFACE = "io.forl.Usage"
# The name the GNOME Shell extension holds while it is turned on.
SHELL_NAME = "io.forl.Shell"

PEER_INTERFACE = "org.freedesktop.DBus.Peer"
INTROSPECTABLE_INTERFACE = "org.freedesktop.DBus.Introspectable"
UNKNOWN_METHOD = "org.freedesktop.DBus.Error.UnknownMethod"
FAILED = "org.freedesktop.DBus.Error.Failed"

# Asked of the bus when the name is requested: fail rather than wait in line
# behind another owner, which only a second copy of the widget would be.
DO_NOT_QUEUE = 4
PRIMARY_OWNER = 1

# How long to wait for the bus to answer, in seconds.
CALL_TIMEOUT = 5.0

INTROSPECTION_XML = """<!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
"http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
<node>
	<interface name="io.forl.Usage">
		<method name="GetStatus"><arg name="status" type="s" direction="out"/></method>
		<method name="Open"><arg name="service" type="s" direction="in"/><arg name="view" type="s" direction="in"/></method>
		<signal name="StatusChanged"><arg name="status" type="s"/></signal>
	</interface>
</node>
"""


class StatusService:
	"""The widget's object on the session bus, and the thread that answers for it."""

	def __init__(self, on_open: Callable[[str, str], None], on_shell_change: Callable[[bool], None]) -> None:
		"""Describe the service without putting it on the bus yet.

		Args:
			on_open: Called with a service key, or an empty string for the tab
				last shown, and a view, "usage" or "settings", when the panel is
				asked for. Runs on the service's thread. Callable taking two str
				and returning None.
			on_shell_change: Called with whether the extension is now on the
				bus, each time that changes. Runs on the service's thread.
				Callable taking a bool and returning None.

		Returns:
			None.
		"""
		if not callable(on_open):
			raise TypeError("on_open must be callable")
		if not callable(on_shell_change):
			raise TypeError("on_shell_change must be callable")
		self._on_open = on_open
		self._on_shell_change = on_shell_change
		self._status = "{}"
		self._connection: Any = None
		self._router: DBusRouter | None = None
		self._calls: queue.Queue[Message] = queue.Queue()
		self._shell_changes: queue.Queue[Message] = queue.Queue()
		self._filters: list[Any] = []
		self._thread: threading.Thread | None = None
		self._closed = threading.Event()

	def open(self) -> bool:
		"""Put the service on the bus under its name.

		Returns:
			bool: True when the name is held. False when there is no session
			bus or another process holds the name, which leaves the widget
			running without the service.
		"""
		try:
			self._connection = open_dbus_connection("SESSION")
			self._router = DBusRouter(self._connection)
			self._filters.append(self._router.filter(MatchRule(type=MessageType.method_call), queue=self._calls))
			changes = MatchRule(
				type="signal",
				sender="org.freedesktop.DBus",
				interface="org.freedesktop.DBus",
				member="NameOwnerChanged",
			)
			changes.add_arg_condition(0, SHELL_NAME)
			self._filters.append(self._router.filter(changes, queue=self._shell_changes))
			self._router.send_and_get_reply(message_bus.AddMatch(changes), timeout=CALL_TIMEOUT)
			reply = self._router.send_and_get_reply(message_bus.RequestName(BUS_NAME, DO_NOT_QUEUE), timeout=CALL_TIMEOUT)
			if not reply.body or reply.body[0] != PRIMARY_OWNER:
				self.close()
				return False
			self._thread = threading.Thread(target=self._serve, name="forl-bus", daemon=True)
			self._thread.start()
		except (OSError, TimeoutError, RuntimeError, ValueError, KeyError):
			self.close()
			return False
		return True

	def shell_present(self) -> bool:
		"""Return whether the GNOME Shell extension is on the bus.

		Returns:
			bool: True when the extension holds its name. False when it does not,
			or when the bus cannot be asked.
		"""
		if self._router is None:
			return False
		try:
			reply = self._router.send_and_get_reply(message_bus.NameHasOwner(SHELL_NAME), timeout=CALL_TIMEOUT)
		except (OSError, TimeoutError, RuntimeError, ValueError):
			return False
		return bool(reply.body and reply.body[0])

	def publish(self, document: dict[str, Any]) -> None:
		"""Change the status the service answers with, and announce it.

		Args:
			document: Everything status.json holds. dict.

		Returns:
			None.
		"""
		require_type(document, dict, "document")
		status = json.dumps(document)
		if status == self._status:
			return
		self._status = status
		if self._router is None:
			return
		try:
			self._router.send(new_signal(DBusAddress(OBJECT_PATH, interface=INTERFACE), "StatusChanged", "s", (status,)))
		except OSError:
			pass

	def close(self) -> None:
		"""Take the service off the bus.

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
		"""Answer calls, and follow the extension, until the service is closed.

		Returns:
			None. Runs on the service's own thread.
		"""
		while not self._closed.is_set():
			self._follow_shell()
			try:
				message = self._calls.get(timeout=0.5)
			except queue.Empty:
				continue
			try:
				reply = self._answer(message)
			except Exception as exc:
				reply = new_error(message, FAILED, "s", (str(exc),))
			if reply is not None and self._router is not None:
				try:
					self._router.send(reply)
				except OSError:
					return

	def _follow_shell(self) -> None:
		"""Report the extension arriving on the bus or leaving it.

		Returns:
			None.
		"""
		while True:
			try:
				change = self._shell_changes.get_nowait()
			except queue.Empty:
				return
			new_owner = change.body[2] if len(change.body) > 2 else ""
			self._on_shell_change(bool(new_owner))

	def _answer(self, message: Message) -> Message | None:
		"""Return the reply to one call, after doing what it asks.

		Args:
			message: The call. jeepney.low_level.Message.

		Returns:
			Message or None: The reply.
		"""
		fields = message.header.fields
		interface = fields.get(HeaderFields.interface, "")
		member = fields.get(HeaderFields.member, "")
		body = message.body

		if interface == PEER_INTERFACE:
			if member == "GetMachineId":
				return new_method_return(message, "s", ("",))
			return new_method_return(message)
		if interface == INTROSPECTABLE_INTERFACE or member == "Introspect":
			return new_method_return(message, "s", (INTROSPECTION_XML,))
		if member == "GetStatus":
			return new_method_return(message, "s", (self._status,))
		if member == "Open":
			service = body[0] if len(body) > 0 and isinstance(body[0], str) else ""
			view = body[1] if len(body) > 1 and isinstance(body[1], str) else ""
			self._on_open(service, view)
			return new_method_return(message)
		return new_error(message, UNKNOWN_METHOD, "s", (member,))
