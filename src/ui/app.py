"""Wire the poller, the tray icons and the panel into one application.

Tkinter only accepts calls from the thread that created its widgets, while the
poller and every tray icon run their own thread. Every cross thread event is
therefore posted to a queue that the Tk thread drains on a short timer, which is
the only place widgets are touched.

One instance reports on one provider, so two of them can run side by side. The
application also owns the user state the widget has: which usages are shown in
the notification area, and whether a reading is currently in flight.
"""

from __future__ import annotations

import ctypes
import queue
import tkinter as tk
import traceback
from typing import Callable

from ..providers import Provider
from ..usage.poller import PollResult, UsagePoller
from ..usage.snapshot import SESSION_KEY, UsageSnapshot
from ..validation import require_non_empty_str, require_positive_int, require_type
from .formatting import format_reset_at
from .panel import Panel
from .tray import IconReading, MenuOption, TrayIcons

DRAIN_INTERVAL_MS = 120
DEFAULT_POLL_SECONDS = 60
DEFAULT_METRIC_KEY = SESSION_KEY
LOADING_TOOLTIP = "loading"


def _enable_dpi_awareness() -> None:
	"""Ask Windows to scale this process by DPI so the panel renders sharply.

	Returns:
		None. Does nothing when the call is unavailable, as on older builds.
	"""
	try:
		ctypes.windll.shcore.SetProcessDpiAwareness(1)
	except (AttributeError, OSError):
		pass


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
		_enable_dpi_awareness()
		self._events: queue.Queue[Callable[[], None]] = queue.Queue()
		self._snapshot: UsageSnapshot | None = None
		self._sign_in_message = ""
		self._refreshing = False
		self._selected: tuple[str, ...] = (DEFAULT_METRIC_KEY,)
		self._drain_job: str | None = None

		self._root = tk.Tk()
		self._root.withdraw()
		self._panel = Panel(self._root, provider, poll_seconds)
		self._tray = TrayIcons(
			provider.key,
			on_activate=lambda: self._post(self._toggle_panel),
			on_toggle=lambda key: self._post(lambda: self._toggle_metric(key)),
			on_quit=lambda: self._post(self.shutdown),
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
		# says the rest.
		self._sign_in_message = result.error if result.needs_sign_in and result.error else ""
		if result.ok:
			self._snapshot = result.snapshot
		self._refresh_surfaces()

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
		self._refresh_surfaces()

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
			self._tray.set_menu((), frozenset(self._selected))
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
		self._tray.set_menu(
			tuple(MenuOption(metric.key, metric.label, metric.group) for metric in metrics.values()),
			frozenset(displayed),
		)
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
		"""Return the hover text for one icon: its usage and when that resets.

		Hovering an icon is a question about the limit, not about the widget, so a
		failed attempt does not change the answer. The exception is a sign-in
		that has run out, which takes the tooltip because until it is fixed there
		is no answer to give.

		Args:
			key: Key of the usage the icon shows. str, non-empty.

		Returns:
			str: Text such as "Current session: Resets at 2:00 PM".
		"""
		require_non_empty_str(key, "key")
		if self._sign_in_message:
			return self._sign_in_message
		metric = self._snapshot.metric(key) if self._snapshot is not None else None
		if metric is None:
			return f"{self._provider.label} usage: {LOADING_TOOLTIP}"
		reset = format_reset_at(metric.resets_at) or "no reset time reported"
		return f"{metric.label}: {reset}"

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
		try:
			self._root.mainloop()
		finally:
			self._poller.stop()
			self._root.destroy()
