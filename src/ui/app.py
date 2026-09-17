"""Wire the poller, the tray icons and the panel into one application.

Tkinter only accepts calls from the thread that created its widgets, while the
poller and every tray icon run their own thread. Every cross thread event is
therefore posted to a queue that the Tk thread drains on a short timer, which is
the only place widgets are touched.

One instance reports on one provider, so two of them can run side by side. The
application also owns the user state the widget has: which usages are shown in
the notification area, and whether a reading is currently in flight.

The part of that state which outlives the process, the chosen usages and their
order and whether the widget starts with Windows, is read once at launch and
written back whenever it changes. The panel and the menu only report what the
user did; deciding what it means and storing it happens here.

The sign-in belongs here too. A launch with nothing stored opens the browser,
and so does a reading that says the sign-in has run out, but only once for each
spell of being signed out and never after the user signed out on purpose. The
sign-in blocks for as long as the user takes over it, so it runs on a thread of
its own and reports back through the same queue as everything else.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
import traceback
import webbrowser
from dataclasses import replace
from typing import Callable

from ..auth import store as credentials
from ..providers import Provider
from ..settings.store import Preferences, load as load_preferences, save as save_preferences
from ..system import enable_dpi_awareness, set_startup_entry
from ..usage.errors import CredentialsError, UsageRequestError
from ..usage.poller import PollResult, UsagePoller
from ..usage.snapshot import LIMIT_GROUP, PRODUCT_GROUP, SESSION_KEY, UsageSnapshot
from ..validation import require_non_empty_str, require_positive_int, require_type
from .formatting import format_icon_tooltip
from .menu import SEPARATOR, MenuRow, TrayMenu
from .panel import SETTINGS_VIEW, Panel
from .tray import IconReading, TrayIcons

DRAIN_INTERVAL_MS = 120
DEFAULT_POLL_SECONDS = 60
DEFAULT_METRIC_KEY = SESSION_KEY
LOADING_TOOLTIP = "Loading"
QUIT_KEY = "quit"
QUIT_LABEL = "Quit"
SETTINGS_KEY = "settings"
SETTINGS_LABEL = "Settings"

SIGNING_IN_TEXT = "Signing in. Finish in the browser."
NO_BROWSER_TEXT = "No browser opened. Use the address below."
SIGNED_OUT_TEXT = "Signed out."


class WidgetApp:
	"""The running widget: one poller, a set of tray icons and one panel."""

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

		self._provider = provider
		enable_dpi_awareness()
		self._events: queue.Queue[Callable[[], None]] = queue.Queue()
		self._snapshot: UsageSnapshot | None = None
		self._sign_in_message = ""
		self._sign_in_prompted = False
		self._signing_in = False
		# The address the sign-in under way is waiting at, kept so the panel can
		# offer it and so a click on it has somewhere to go.
		self._sign_in_link = ""
		# Set when the user signs out, which is the one case where being signed
		# out must not put a browser window in front of them.
		self._signed_out = False
		self._refreshing = False
		self._drain_job: str | None = None

		self._preferences = load_preferences(provider.key)
		self._selected: tuple[str, ...] = self._preferences.views or (DEFAULT_METRIC_KEY,)
		# Written at every launch rather than only when the switch is worked, so
		# an entry naming a folder the widget has since been moved out of is
		# corrected instead of failing quietly at the next sign-in.
		set_startup_entry(provider.key, self._preferences.start_on_startup)

		self._root = tk.Tk()
		self._root.withdraw()
		self._panel = Panel(
			self._root,
			provider,
			poll_seconds,
			on_startup_change=self._set_startup,
			on_sign_in=self._sign_in_now,
			on_sign_out=self._sign_out,
			on_open_sign_in=self._open_sign_in_link,
		)
		self._panel.set_startup(self._preferences.start_on_startup)
		self._show_account()
		self._menu = TrayMenu(self._root, provider.accent, on_choose=self._choose)
		self._tray = TrayIcons(
			provider,
			on_activate=lambda: self._post(self._toggle_panel),
			on_menu=lambda x, y: self._post(lambda: self._open_menu(x, y)),
		)
		self._poller = UsagePoller(
			read=provider.read,
			on_result=self._on_poll_result,
			on_begin=lambda: self._post(self._on_poll_begin),
			interval_seconds=poll_seconds,
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

	def _on_poll_begin(self) -> None:
		"""Mark a reading as in flight and show that in both surfaces.

		Returns:
			None.
		"""
		self._refreshing = True
		self._refresh_surfaces()

	def _on_poll_result(self, result: PollResult) -> None:
		"""Accept a reading from the poller thread and schedule the redraw.

		Args:
			result: The outcome of one polling attempt. PollResult.

		Returns:
			None.
		"""
		self._post(lambda: self._apply_result(result))

	def _apply_result(self, result: PollResult) -> None:
		"""Store a reading and refresh both surfaces.

		A failed attempt keeps the previous snapshot on screen. Only one the user
		can fix, by signing in again, is reported; a brief network problem
		neither blanks the icons nor puts a message in front of them.

		Args:
			result: The outcome of one polling attempt. PollResult.

		Returns:
			None.
		"""
		self._refreshing = False
		# Only a failure the user can act on is kept. Anything else is dropped:
		# the reading on screen is still the last good one, and how old it is
		# says the rest. A sign-in the user is in the middle of, or has just
		# stepped out of, keeps the line: it says more than the reading's
		# complaint that there is no sign-in to read with.
		if not self._signing_in and not self._signed_out:
			self._sign_in_message = result.error if result.needs_sign_in and result.error else ""
		if result.ok:
			self._snapshot = result.snapshot
		self._prompt_sign_in()
		self._refresh_surfaces()

	def _prompt_sign_in(self) -> None:
		"""Put the user in front of the sign-in when a reading says one is needed.

		Started once for each spell of being signed out rather than at every
		reading, so a sign-in left undone does not raise a browser window a
		minute, and never after the user signed out on purpose.

		Returns:
			None.
		"""
		if not self._sign_in_message:
			self._sign_in_prompted = False
			return
		if self._sign_in_prompted or self._signed_out:
			return
		self._sign_in_prompted = True
		self._sign_in_now()

	def _stored_sign_in(self) -> tuple[str, bool]:
		"""Return who is signed in, and whether anyone is.

		Returns:
			tuple[str, bool]: The account as the settings should name them, empty
			when the sign-in reported no name, and whether there is a sign-in at
			all.
		"""
		tokens = credentials.load(self._provider.key)
		return (tokens.account if tokens is not None else "", tokens is not None)

	def _show_account(self) -> None:
		"""Tell the panel who is signed in.

		Returns:
			None.
		"""
		account, signed_in = self._stored_sign_in()
		self._panel.set_account(account, signed_in)

	def _sign_in_now(self) -> None:
		"""Sign in through the browser, on a thread of its own.

		Returns:
			None. Does nothing while a sign-in is already under way.
		"""
		if self._signing_in:
			return
		self._signing_in = True
		self._signed_out = False
		self._sign_in_message = SIGNING_IN_TEXT
		self._refresh_surfaces()
		threading.Thread(
			target=self._run_sign_in,
			name=f"forl-sign-in-{self._provider.key}",
			daemon=True,
		).start()

	def _offer_address(self, address: str, opened: bool) -> None:
		"""Take the sign-in address from the sign-in thread to the Tk thread.

		Args:
			address: Where the sign-in is waiting. str.
			opened: Whether a browser was opened at it. bool.

		Returns:
			None. Runs on the sign-in thread.
		"""
		self._post(lambda: self._show_address(address, opened))

	def _show_address(self, address: str, opened: bool) -> None:
		"""Put the sign-in address in front of the user.

		Offered whether or not a browser opened, because one that opened may
		still have opened somewhere the user cannot see.

		Args:
			address: Where the sign-in is waiting. str.
			opened: Whether a browser was opened at it, which is the difference
				between telling the user to finish and telling them to start.
				bool.

		Returns:
			None.
		"""
		require_type(address, str, "address")
		require_type(opened, bool, "opened")
		self._sign_in_link = address
		self._sign_in_message = SIGNING_IN_TEXT if opened else NO_BROWSER_TEXT
		self._panel.set_sign_in_link(address)
		self._refresh_surfaces()

	def _open_sign_in_link(self) -> None:
		"""Open the sign-in address in a browser, if one can be opened.

		Returns:
			None. The panel has already put the address on the clipboard, which
			is what is left when no browser opens.
		"""
		if not self._sign_in_link:
			return
		webbrowser.open(self._sign_in_link)

	def _run_sign_in(self) -> None:
		"""Run the provider's sign-in and report the outcome to the Tk thread.

		Returns:
			None. Runs on the sign-in thread.
		"""
		message = ""
		try:
			self._provider.sign_in(self._offer_address)
		except (CredentialsError, UsageRequestError) as exc:
			message = str(exc)
		self._post(lambda: self._finish_sign_in(message))

	def _finish_sign_in(self, message: str) -> None:
		"""Act on the outcome of a sign-in.

		Args:
			message: What went wrong, empty when nothing did. str.

		Returns:
			None.
		"""
		require_type(message, str, "message")
		self._signing_in = False
		self._sign_in_message = message
		self._forget_address()
		self._show_account()
		if not message:
			# The reading on screen, if there is one, belongs to whoever was
			# signed in before, so it goes rather than stands under the new name.
			self._snapshot = None
			self._poller.refresh()
		self._refresh_surfaces()

	def _sign_out(self) -> None:
		"""Forget the sign-in, and stop reporting until the user signs in again.

		This is also how the widget is moved to another subscription on the same
		machine: sign out of one and in to the other.

		Returns:
			None.
		"""
		credentials.clear(self._provider.key)
		self._signed_out = True
		self._sign_in_prompted = False
		self._snapshot = None
		self._sign_in_message = SIGNED_OUT_TEXT
		self._forget_address()
		self._show_account()
		self._refresh_surfaces()

	def _forget_address(self) -> None:
		"""Withdraw the sign-in address, there being no sign-in to finish.

		Returns:
			None.
		"""
		self._sign_in_link = ""
		self._panel.set_sign_in_link("")

	def _toggle_metric(self, key: str) -> None:
		"""Add a usage to the notification area, or take it away.

		The last displayed usage cannot be removed, because doing so would leave
		no icon to reach the menu from.

		Args:
			key: Key of the usage the user clicked. str, non-empty.

		Returns:
			None.
		"""
		require_non_empty_str(key, "key")
		if key in self._selected:
			if len(self._selected) > 1:
				self._selected = tuple(other for other in self._selected if other != key)
		else:
			self._selected = self._selected + (key,)
		self._store(replace(self._preferences, views=self._selected))
		self._refresh_surfaces()

	def _store(self, preferences: Preferences) -> None:
		"""Keep a set of preferences and write it to disk.

		Args:
			preferences: The values to keep. Preferences.

		Returns:
			None. A file that cannot be written costs the user the choice at the
			next launch and nothing in this one, so it is not reported.
		"""
		require_type(preferences, Preferences, "preferences")
		self._preferences = preferences
		save_preferences(self._provider.key, preferences)

	def _set_startup(self, enabled: bool) -> None:
		"""Store whether this widget starts with Windows, and make it so.

		Args:
			enabled: What the user set the switch to. bool.

		Returns:
			None. The switch is put back when the system refuses the change.
		"""
		require_type(enabled, bool, "enabled")
		if not set_startup_entry(self._provider.key, enabled):
			# Nothing was registered, so the switch is put back rather than left
			# claiming something that is not so.
			self._panel.set_startup(self._preferences.start_on_startup)
			return
		self._store(replace(self._preferences, start_on_startup=enabled))

	def _menu_rows(self) -> tuple[MenuRow, ...]:
		"""Return the lines of the menu for the reading on screen.

		Returns:
			tuple of MenuRow: One line per usage the account reports, grouped into
			limits and products, then the settings and the command to quit, each
			in a section of its own.
		"""
		rows: list[MenuRow] = []
		if self._snapshot is not None:
			displayed = frozenset(self._displayed_keys())
			for group in (LIMIT_GROUP, PRODUCT_GROUP):
				entries = [metric for metric in self._snapshot.metrics() if metric.group == group]
				if not entries:
					continue
				rows.extend(MenuRow(entry.key, entry.label, entry.key in displayed) for entry in entries)
				rows.append(MenuRow(SEPARATOR, "", False))
		rows.append(MenuRow(SETTINGS_KEY, SETTINGS_LABEL, False))
		rows.append(MenuRow(SEPARATOR, "", False))
		rows.append(MenuRow(QUIT_KEY, QUIT_LABEL, False))
		return tuple(rows)

	def _open_menu(self, x: int, y: int) -> None:
		"""Open the menu at the pointer.

		Args:
			x: Pointer position across the screen in pixels. int.
			y: Pointer position down the screen in pixels. int.

		Returns:
			None.
		"""
		self._panel.hide()
		self._menu.show(self._menu_rows(), (x, y))

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
			self._panel.update_view(self._snapshot, self._sign_in_message, self._refreshing)
			self._panel.show(SETTINGS_VIEW)
			return
		self._toggle_metric(key)

	def _displayed_keys(self) -> tuple[str, ...]:
		"""Return the selected keys the current reading still reports.

		A scoped limit disappears once its window empties, and a product only
		appears once it has been used, so the selection is filtered against what
		the reading actually carries.

		Returns:
			tuple of str: The keys to draw an icon for, in selection order. Falls
			back to the five hour window when nothing else survives.
		"""
		if self._snapshot is None:
			return ()
		available = {metric.key for metric in self._snapshot.metrics()}
		kept = tuple(key for key in self._selected if key in available)
		return kept or (DEFAULT_METRIC_KEY,)

	def _refresh_surfaces(self) -> None:
		"""Redraw the tray icons and, when it is open, the panel.

		Returns:
			None.
		"""
		self._panel.update_view(self._snapshot, self._sign_in_message, self._refreshing)

		if self._snapshot is None:
			self._tray.sync(
				(
					IconReading(
						key=DEFAULT_METRIC_KEY,
						percent=None,
						tooltip=self._sign_in_message or f"{self._provider.label} usage: {LOADING_TOOLTIP}",
					),
				)
			)
			return

		metrics = {metric.key: metric for metric in self._snapshot.metrics()}
		displayed = self._displayed_keys()
		self._tray.sync(
			tuple(
				IconReading(
					key=key,
					percent=metrics[key].percent,
					tooltip=self._tooltip(key),
				)
				for key in displayed
				if key in metrics
			)
		)

	def _tooltip(self, key: str) -> str:
		"""Return the hover text for one icon: its reading and which limit it is.

		Hovering an icon is a question about the limit, not about the widget, so a
		failed attempt does not change the answer. The exception is a sign-in
		that has run out, which takes the tooltip because until it is fixed there
		is no answer to give.

		Args:
			key: Key of the usage the icon shows. str, non-empty.

		Returns:
			str: Text such as "34% - Current session".
		"""
		require_non_empty_str(key, "key")
		if self._sign_in_message:
			return self._sign_in_message
		metric = self._snapshot.metric(key) if self._snapshot is not None else None
		if metric is None:
			return f"{self._provider.label} usage: {LOADING_TOOLTIP}"
		return format_icon_tooltip(metric.percent, metric.label)

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
		self._panel.update_view(self._snapshot, self._sign_in_message, self._refreshing)
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
		self._poller.stop()
		self._tray.stop()
		self._root.quit()

	def run(self) -> None:
		"""Start polling, show the icons and block on the Tk event loop.

		Returns:
			None. Returns once the user quits the widget.
		"""
		self._refresh_surfaces()
		self._tray.start()
		self._poller.start()
		self._drain_job = self._root.after(DRAIN_INTERVAL_MS, self._drain_events)
		if credentials.load(self._provider.key) is None:
			# Nothing stored, so there is nothing to read with until the user has
			# been through the browser. Started here rather than in the
			# constructor so the icon is already in the notification area by the
			# time the browser window appears in front of it.
			self._sign_in_now()
		try:
			self._root.mainloop()
		finally:
			self._poller.stop()
			self._root.destroy()
