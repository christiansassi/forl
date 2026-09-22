"""Wire the Windows surfaces to the shared widget state.

Everything that is not drawing, the poller, the sign-in, the selection and the
preferences, lives in core.py and serves both platforms. What is here is the
Windows half: a Tk root, the notification area icons, the menu drawn in place of
the shell's own, and the panel.

One process watches every service, the way the Mac app does. Each service has a
core of its own and a set of tray icons of its own, drawn in its color; the panel
and the menu are shared, and the panel shows one service at a time under a row
of tabs. A service nobody is signed in to has no icons.

One more icon, in the app's own artwork, stands in whenever no usage icon is
showing: with nobody signed in, or with every usage unchecked. It opens the panel
and carries the menu that quits the widget, so the widget can always be reached
from the tray, and it goes away as soon as a usage icon takes its place.

Tkinter only accepts calls from the thread that created its widgets, while the
pollers and every tray icon run their own threads. Every cross thread event is
therefore posted to a queue that the Tk thread drains on a short timer, which is
the only place widgets are touched, and that queue is what each core is given to
dispatch with.
"""

from __future__ import annotations

import queue
import tkinter as tk
import traceback
from functools import lru_cache
from typing import Callable

from PIL import Image

from ..providers import Provider
from ..render.icon import render_icon
from ..render.svg import ASSETS_DIR
from ..render.theme import LABEL_PRIMARY
from ..settings.store import load_start_on_startup, save_start_on_startup
from ..system import enable_dpi_awareness, set_startup_entry
from ..validation import require_member, require_non_empty_str, require_positive_int, require_type
from .core import DEFAULT_POLL_SECONDS, QUIT_KEY, MetricReading, ProviderView, WidgetCore, quit_rows
from .menu import TrayMenu
from .panel import USAGE_VIEW, Panel
from .tray import TrayIcons

DRAIN_INTERVAL_MS = 120
# How often each service is asked whether its session start is due. Well under a
# minute, so a schedule with no grace still has its one minute checked, which a
# reading once a minute, a little late each time, could step over.
SESSION_START_CHECK_MS = 20_000

# The icon shown while no usage icon is, drawn from the app's own artwork.
APP_ICON_NAME = "forl"
APP_ICON_KEY = "app"
APP_ICON_TOOLTIP = "FORL"
APP_ICON_SIGNED_OUT_TOOLTIP = "FORL: not signed in"
APP_ICON_FILE = "icon.png"


@lru_cache(maxsize=4)
def _app_artwork(size: int) -> Image.Image:
	"""Return the app's own artwork at the size of a tray icon.

	Args:
		size: Edge length in pixels. int, greater than 0.

	Returns:
		PIL.Image.Image: The artwork, mode "RGBA", reduced to size by size.
	"""
	require_positive_int(size, "size")
	with Image.open(ASSETS_DIR / APP_ICON_FILE) as source:
		return source.convert("RGBA").resize((size, size), Image.LANCZOS)


class WidgetApp:
	"""The running widget: one core and one set of icons per service, and one panel."""

	def __init__(self, providers: tuple[Provider, ...], poll_seconds: int = DEFAULT_POLL_SECONDS) -> None:
		"""Build the application without starting the pollers or showing an icon.

		Args:
			providers: Every service to watch, in the order their tabs appear.
				tuple of Provider, non-empty.
			poll_seconds: Delay between usage readings. int, greater than 0.

		Returns:
			None.
		"""
		require_type(providers, tuple, "providers")
		if not providers:
			raise ValueError("providers must not be empty")
		for provider in providers:
			require_type(provider, Provider, "providers")
		require_positive_int(poll_seconds, "poll_seconds")

		enable_dpi_awareness()
		self._events: queue.Queue[Callable[[], None]] = queue.Queue()
		self._drain_job: str | None = None
		self._session_start_job: str | None = None
		# Set once shutdown starts, so a drain that is running the shutdown does
		# not schedule itself again on a window about to be destroyed.
		self._stopping = False
		self._providers = providers
		self._keys = frozenset(provider.key for provider in providers)
		self._start_on_startup = load_start_on_startup()
		# Written at every launch rather than only when the switch is worked, so
		# an entry naming a folder the widget has since been moved out of is
		# corrected, and the entries of the version that ran one process per
		# service are cleared, instead of either failing quietly at sign-in.
		set_startup_entry(self._start_on_startup)

		self._root = tk.Tk()
		self._root.withdraw()
		self._cores = {
			provider.key: WidgetCore(
				provider,
				dispatch=self._post,
				on_change=self._refresh_surfaces,
				poll_seconds=poll_seconds,
			)
			for provider in providers
		}
		self._panel = Panel(
			self._root,
			providers,
			describe=self._describe,
			on_startup_change=self._set_startup,
			on_sign_in=lambda key: self._core(key).sign_in_now(),
			on_sign_out=lambda key: self._core(key).sign_out(),
			on_open_sign_in=lambda key: self._core(key).open_sign_in_link(),
			on_toggle_metric=lambda key, metric: self._core(key).toggle_metric(metric),
			on_session_start_change=lambda key, schedule: self._core(key).set_session_start(schedule),
		)
		self._panel.set_startup(self._start_on_startup)
		self._menu = TrayMenu(self._root, on_choose=self._choose)
		self._trays = {provider.key: self._tray_for(provider) for provider in providers}
		self._app_icon = TrayIcons(
			APP_ICON_NAME,
			lambda _percent, size: _app_artwork(size),
			on_activate=lambda: self._post(lambda: self._toggle_panel("")),
			on_menu=lambda x, y: self._post(lambda: self._open_menu(x, y)),
		)

	def _tray_for(self, provider: Provider) -> TrayIcons:
		"""Return the set of icons one service's readings are shown in.

		The icons are named by the service's key, which is what they were named
		by when each service ran in a process of its own, so Windows keeps them
		where the user put them.

		Args:
			provider: The service. Provider.

		Returns:
			TrayIcons: The icons, none of them showing yet.
		"""
		key = provider.key
		return TrayIcons(
			key,
			lambda percent, size: render_icon(percent, size, provider.accent),
			on_activate=lambda: self._post(lambda: self._toggle_panel(key)),
			on_menu=lambda x, y: self._post(lambda: self._open_menu(x, y)),
		)

	def _core(self, provider_key: str) -> WidgetCore:
		"""Return the core that watches one service.

		Args:
			provider_key: Key of the service. str, non-empty.

		Returns:
			WidgetCore: Its core.
		"""
		require_member(provider_key, self._keys, "provider_key")
		return self._cores[provider_key]

	def _describe(self, provider_key: str) -> ProviderView:
		"""Return everything the panel draws for one service.

		Args:
			provider_key: Key of the service. str, non-empty.

		Returns:
			ProviderView: The state of that service now.
		"""
		return self._core(provider_key).view()

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
			if not self._stopping:
				self._drain_job = self._root.after(DRAIN_INTERVAL_MS, self._drain_events)

	def _check_session_starts(self) -> None:
		"""Ask every service whether its session start is due, then reschedule.

		Returns:
			None.
		"""
		try:
			for core in self._cores.values():
				core.check_session_start()
		finally:
			if not self._stopping:
				self._session_start_job = self._root.after(SESSION_START_CHECK_MS, self._check_session_starts)

	def _set_startup(self, enabled: bool) -> None:
		"""Store whether the widget starts with Windows, and make it so.

		Args:
			enabled: What the user set the switch to. bool.

		Returns:
			None. The switch is put back when the system refuses the change.
		"""
		require_type(enabled, bool, "enabled")
		if not set_startup_entry(enabled):
			# Nothing was registered, so the switch is put back rather than left
			# claiming something that is not so.
			self._panel.set_startup(self._start_on_startup)
			return
		self._start_on_startup = enabled
		save_start_on_startup(enabled)

	def _open_menu(self, x: int, y: int) -> None:
		"""Open the menu of a tray icon at the pointer.

		Every icon opens the same menu, which only quits: the usages are chosen
		in the Show section of the settings.

		Args:
			x: Pointer position across the screen in pixels. int.
			y: Pointer position down the screen in pixels. int.

		Returns:
			None.
		"""
		self._panel.hide()
		self._menu.show(quit_rows(), (x, y), LABEL_PRIMARY)

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

	def _refresh_surfaces(self) -> None:
		"""Redraw every tray icon and, when it is open, the panel.

		Returns:
			None.
		"""
		self._panel.refresh()
		showing = False
		for key, tray in self._trays.items():
			readings = self._cores[key].readings()
			showing = showing or bool(readings)
			tray.sync(readings)
		if showing:
			self._app_icon.sync(())
			return
		anyone = any(core.signed_in for core in self._cores.values())
		self._app_icon.sync(
			(MetricReading(APP_ICON_KEY, None, APP_ICON_TOOLTIP if anyone else APP_ICON_SIGNED_OUT_TOOLTIP),)
		)

	def _toggle_panel(self, provider_key: str) -> None:
		"""Open the panel on a service's tab, or dismiss it when it is already open.

		Clicking an icon moves focus off the panel, which dismisses it before the
		click reaches here, so a panel that has only just gone away counts as
		having been open: the click closes it rather than closing and reopening
		it in one motion.

		Args:
			provider_key: Key of the service whose icon was clicked, or an empty
				string to open on the tab last shown. str.

		Returns:
			None.
		"""
		require_type(provider_key, str, "provider_key")
		if self._panel.visible or self._panel.dismissed_by_this_click():
			self._panel.hide()
			return
		self._panel.show(USAGE_VIEW, provider_key)

	def shutdown(self) -> None:
		"""Stop the pollers, remove the tray icons and end the Tk loop.

		Every repeating timer is cancelled first, so nothing is left scheduled
		against a window that is about to be destroyed.

		Returns:
			None.
		"""
		self._stopping = True
		if self._drain_job is not None:
			self._root.after_cancel(self._drain_job)
			self._drain_job = None
		if self._session_start_job is not None:
			self._root.after_cancel(self._session_start_job)
			self._session_start_job = None
		self._menu.hide()
		self._panel.hide()
		for core in self._cores.values():
			core.stop()
		for tray in (self._app_icon, *self._trays.values()):
			tray.stop()
		self._root.quit()

	def run(self) -> None:
		"""Start polling, show the icons and block on the Tk event loop.

		Returns:
			None. Returns once the user quits the widget.
		"""
		self._refresh_surfaces()
		for tray in (self._app_icon, *self._trays.values()):
			tray.start()
		self._drain_job = self._root.after(DRAIN_INTERVAL_MS, self._drain_events)
		self._session_start_job = self._root.after(SESSION_START_CHECK_MS, self._check_session_starts)
		for core in self._cores.values():
			core.start()
		if not any(core.signed_in for core in self._cores.values()):
			# Nobody is signed in, so there is nothing in the notification area
			# worth finding; the panel is put in front of the user instead, on
			# the page that starts a sign-in, as the Mac app does.
			self._root.after(DRAIN_INTERVAL_MS, lambda: self._panel.show(USAGE_VIEW))
		try:
			self._root.mainloop()
		finally:
			for core in self._cores.values():
				core.stop()
			self._root.destroy()
