"""Wire the Windows surfaces to the shared widget state.

Everything that is not drawing, the poller, the sign-in, the selection and the
preferences, lives in core.py and serves both platforms. What is here is the
Windows half: a Tk root, the notification area icons, the menu drawn in place of
the shell's own, and the panel.

Tkinter only accepts calls from the thread that created its widgets, while the
poller and every tray icon run their own thread. Every cross thread event is
therefore posted to a queue that the Tk thread drains on a short timer, which is
the only place widgets are touched, and that queue is what the core is given to
dispatch with.
"""

from __future__ import annotations

import queue
import tkinter as tk
import traceback
from typing import Callable

from ..providers import Provider
from ..system import enable_dpi_awareness
from ..validation import require_non_empty_str, require_positive_int, require_type
from .core import DEFAULT_POLL_SECONDS, QUIT_KEY, SETTINGS_KEY, WidgetCore
from .menu import TrayMenu
from .panel import SETTINGS_VIEW, Panel
from .tray import TrayIcons

DRAIN_INTERVAL_MS = 120


class WidgetApp:
	"""The running widget: one core, a set of tray icons and one panel."""

	def __init__(self, provider: Provider, poll_seconds: int = DEFAULT_POLL_SECONDS) -> None:
		"""Build the application without starting the poller or showing an icon.

		Args:
			provider: The service to report on. Provider.
			poll_seconds: Delay between usage readings. int, greater than 0.

		Returns:
			None.
		"""
		require_type(provider, Provider, "provider")
		require_positive_int(poll_seconds, "poll_seconds")

		enable_dpi_awareness()
		self._events: queue.Queue[Callable[[], None]] = queue.Queue()
		self._drain_job: str | None = None

		self._root = tk.Tk()
		self._root.withdraw()
		self._core = WidgetCore(
			provider,
			dispatch=self._post,
			on_change=self._refresh_surfaces,
			poll_seconds=poll_seconds,
		)
		self._panel = Panel(
			self._root,
			provider,
			status_text=self._core.status_text,
			on_startup_change=self._set_startup,
			on_sign_in=self._core.sign_in_now,
			on_sign_out=self._core.sign_out,
			on_open_sign_in=self._core.open_sign_in_link,
		)
		self._panel.set_startup(self._core.preferences.start_on_startup)
		self._menu = TrayMenu(self._root, provider.accent, on_choose=self._choose)
		self._tray = TrayIcons(
			provider,
			on_activate=lambda: self._post(self._toggle_panel),
			on_menu=lambda x, y: self._post(lambda: self._open_menu(x, y)),
		)

	def _post(self, action: Callable[[], None]) -> None:
		"""Queue an action to run on the Tk thread.

		Args:
			action: The work to perform. Callable taking no arguments and
				returning None.

		Returns:
			None.
		"""
		self._events.put(action)

	def _drain_events(self) -> None:
		"""Run every queued action, then reschedule this drain.

		An action that raises is reported and skipped rather than allowed to
		escape, because escaping would leave this drain unscheduled and stop the
		widget from ever updating again.

		Returns:
			None.
		"""
		try:
			while True:
				try:
					action = self._events.get_nowait()
				except queue.Empty:
					break
				try:
					action()
				except Exception:
					traceback.print_exc()
		finally:
			self._drain_job = self._root.after(DRAIN_INTERVAL_MS, self._drain_events)

	def _set_startup(self, enabled: bool) -> None:
		"""Store whether this widget starts with Windows, and make it so.

		Args:
			enabled: What the user set the switch to. bool.

		Returns:
			None. The switch is put back when the system refuses the change.
		"""
		require_type(enabled, bool, "enabled")
		if not self._core.set_startup(enabled):
			# Nothing was registered, so the switch is put back rather than left
			# claiming something that is not so.
			self._panel.set_startup(self._core.preferences.start_on_startup)

	def _open_menu(self, x: int, y: int) -> None:
		"""Open the menu at the pointer.

		Args:
			x: Pointer position across the screen in pixels. int.
			y: Pointer position down the screen in pixels. int.

		Returns:
			None.
		"""
		self._panel.hide()
		self._menu.show(self._core.menu_rows(), (x, y))

	def _choose(self, key: str) -> None:
		"""Act on the line the user picked from the menu.

		Args:
			key: The key of the chosen line. str, non-empty.

		Returns:
			None.
		"""
		require_non_empty_str(key, "key")
		if key == QUIT_KEY:
			self.shutdown()
			return
		if key == SETTINGS_KEY:
			self._update_panel()
			self._panel.show(SETTINGS_VIEW)
			return
		self._core.toggle_metric(key)

	def _update_panel(self) -> None:
		"""Hand the panel everything it draws from.

		Returns:
			None.
		"""
		account, signed_in = self._core.account()
		self._panel.set_account(account, signed_in)
		self._panel.set_sign_in_link(self._core.sign_in_link)
		self._panel.set_startup(self._core.preferences.start_on_startup)
		self._panel.update_view(self._core.snapshot, self._core.sign_in_message, self._core.refreshing)

	def _refresh_surfaces(self) -> None:
		"""Redraw the tray icons and, when it is open, the panel.

		Returns:
			None.
		"""
		self._update_panel()
		self._tray.sync(self._core.readings())

	def _toggle_panel(self) -> None:
		"""Open the panel, or dismiss it when it is already open.

		Clicking an icon moves focus off the panel, which dismisses it before the
		click reaches here, so a panel that has only just gone away counts as
		having been open: the click closes it rather than closing and reopening
		it in one motion.

		Returns:
			None.
		"""
		if self._panel.visible or self._panel.dismissed_by_this_click():
			self._panel.hide()
			return
		self._update_panel()
		self._panel.show()

	def shutdown(self) -> None:
		"""Stop the poller, remove the tray icons and end the Tk loop.

		Every repeating timer is cancelled first, so nothing is left scheduled
		against a window that is about to be destroyed.

		Returns:
			None.
		"""
		if self._drain_job is not None:
			self._root.after_cancel(self._drain_job)
			self._drain_job = None
		self._menu.hide()
		self._panel.hide()
		self._core.stop()
		self._tray.stop()
		self._root.quit()

	def run(self) -> None:
		"""Start polling, show the icons and block on the Tk event loop.

		Returns:
			None. Returns once the user quits the widget.
		"""
		self._refresh_surfaces()
		self._tray.start()
		self._drain_job = self._root.after(DRAIN_INTERVAL_MS, self._drain_events)
		# Started after the icons are up, so a browser window raised by a launch
		# with nothing stored appears in front of a widget that is already there.
		self._core.start()
		try:
			self._root.mainloop()
		finally:
			self._core.stop()
			self._root.destroy()
