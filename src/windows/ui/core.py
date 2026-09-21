"""Everything the widget does that is not drawing.

Two platforms draw this widget and both do the same bookkeeping behind it: hold
the last reading, remember which usages the user chose and in what order, run
the browser sign-in on a thread and keep track of where it got to, write the
preferences back, and work out what each surface should say. That is here, once,
with no toolkit in it.

A platform supplies two functions and takes the rest. `dispatch` runs a call on
whichever thread owns the interface, since the poller and the sign-in each have
a thread of their own and neither may touch a window. `on_change` is called from
that thread whenever something a surface shows has changed, and is the only
signal a platform needs to redraw.

One core watches one service, and the widget holds one core per service, the
way the Mac app holds one provider state per service. A service nobody has
signed in to is never sent to the browser on its own: the panel offers the
sign-in and the user starts it. Only a sign-in that was working and has run out
opens the browser by itself, once, so the reading comes back without a trip
through the settings.
"""

from __future__ import annotations

import threading
import webbrowser
from dataclasses import replace
from typing import Callable, NamedTuple

from ..auth import store as credentials
from ..providers import Provider
from ..settings.store import Preferences, load as load_preferences, save as save_preferences
from ..usage.errors import CredentialsError, UsageRequestError
from ..usage.poller import PollResult, UsagePoller
from ..usage.snapshot import LIMIT_GROUP, PRODUCT_GROUP, SESSION_KEY, Metric, UsageSnapshot, now_utc
from ..validation import require_non_empty_str, require_positive_int, require_type
from .formatting import format_icon_tooltip, format_next_update

DEFAULT_POLL_SECONDS = 60
DEFAULT_METRIC_KEY = SESSION_KEY

LOADING_TEXT = "Loading"

# The key a menu row carries when it is a rule rather than a choice.
SEPARATOR = "separator"

QUIT_KEY = "quit"
QUIT_LABEL = "Quit FORL"

NOT_SIGNED_IN_TEXT = "Not signed in"

SIGNING_IN_TEXT = "Signing in. Finish in the browser."
NO_BROWSER_TEXT = "No browser opened. Use the address below."
SIGNED_OUT_TEXT = "Signed out."


class MenuRow(NamedTuple):
	"""One line of the menu both platforms open on a right click.

	Attributes:
		key: What to report when the line is chosen, or SEPARATOR for a rule. str.
		label: The text of the line, empty for a rule. str.
		checked: Whether the line carries a check mark, which is how a usage
			already being shown is marked. bool.
	"""

	key: str
	label: str
	checked: bool


class MetricReading(NamedTuple):
	"""What one small surface, a tray icon or a menu bar item, should show.

	Attributes:
		key: Stable identifier of the usage the surface stands for. str.
		percent: Share already used, 0 to 100, or None before the first reading
			has arrived. float or None.
		tooltip: Hover text, which names the reading and the limit it belongs to.
			str.
	"""

	key: str
	percent: float | None
	tooltip: str


class ProviderView(NamedTuple):
	"""Everything the panel draws for one service, taken at one moment.

	Attributes:
		provider: The service. Provider.
		snapshot: The last reading, or None before one and after a sign-out.
			UsageSnapshot or None.
		status: The line under the reading, which is the sign-in instruction or
			the countdown to the next reading. str.
		sign_in_message: What to say about the sign-in, empty when there is
			nothing to say. str.
		sign_in_link: The address a sign-in under way is waiting at, empty when
			none is. str.
		refreshing: Whether a reading is in flight. bool.
		signed_in: Whether a sign-in is stored for the service. bool.
		signing_in: Whether a browser sign-in is under way. bool.
		account: Who is signed in, as the settings name them, empty when the
			sign-in reported no name. str.
		groups: Every usage the reading reports, grouped as the panel groups
			them, which is what the Show section lists. tuple of tuple of Metric.
		displayed: Keys of the usages the tray icons show, which is what the
			Show section checks. frozenset of str.
	"""

	provider: Provider
	snapshot: UsageSnapshot | None
	status: str
	sign_in_message: str
	sign_in_link: str
	refreshing: bool
	signed_in: bool
	signing_in: bool
	account: str
	groups: tuple[tuple[Metric, ...], ...]
	displayed: frozenset[str]


def quit_rows() -> tuple[MenuRow, ...]:
	"""Return the lines of the menu a right click on a tray icon opens.

	Which usages the icons show is chosen in the Show section of the settings,
	so the menu is left with the one thing the panel does not offer.

	Returns:
		tuple of MenuRow: The one line that quits the widget.
	"""
	return (MenuRow(QUIT_KEY, QUIT_LABEL, False),)


class WidgetCore:
	"""The state of one service: one provider, one poller, one selection."""

	def __init__(
		self,
		provider: Provider,
		dispatch: Callable[[Callable[[], None]], None],
		on_change: Callable[[], None],
		poll_seconds: int = DEFAULT_POLL_SECONDS,
	) -> None:
		"""Build the state without starting the poller.

		Args:
			provider: The service to report on. Provider.
			dispatch: Runs a call on the thread that owns the interface. Called
				from the poller thread and from the sign-in thread. Callable
				taking one callable and returning None.
			on_change: Called on the interface thread whenever something a
				surface shows has changed. Callable taking no arguments and
				returning None.
			poll_seconds: Delay between usage readings. int, greater than 0.

		Returns:
			None.
		"""
		require_type(provider, Provider, "provider")
		for name, callback in (("dispatch", dispatch), ("on_change", on_change)):
			if not callable(callback):
				raise TypeError(f"{name} must be callable")
		require_positive_int(poll_seconds, "poll_seconds")

		self._provider = provider
		self._dispatch = dispatch
		self._on_change = on_change
		self._poll_seconds = poll_seconds

		self._snapshot: UsageSnapshot | None = None
		self._sign_in_message = ""
		self._sign_in_prompted = False
		self._signing_in = False
		# The address the sign-in under way is waiting at, kept so a surface can
		# offer it and so a click on it has somewhere to go.
		self._sign_in_link = ""
		# Set when the user signs out, which is the one case where being signed
		# out must not put a browser window in front of them.
		self._signed_out = False
		self._refreshing = False

		self._preferences = load_preferences(provider.key)
		views = self._preferences.views
		self._selected: tuple[str, ...] = views if views is not None else (DEFAULT_METRIC_KEY,)

		self._poller = UsagePoller(
			read=provider.read,
			on_result=lambda result: self._dispatch(lambda: self._apply_result(result)),
			on_begin=lambda: self._dispatch(self._begin_poll),
			interval_seconds=poll_seconds,
		)

	@property
	def provider(self) -> Provider:
		"""Return the service being reported on.

		Returns:
			Provider: The provider this widget was built for.
		"""
		return self._provider

	@property
	def poll_seconds(self) -> int:
		"""Return the delay between readings.

		Returns:
			int: The interval in seconds.
		"""
		return self._poll_seconds

	@property
	def snapshot(self) -> UsageSnapshot | None:
		"""Return the last reading that arrived.

		Returns:
			UsageSnapshot or None: The reading, or None before the first one has
			arrived and after a sign-out.
		"""
		return self._snapshot

	@property
	def preferences(self) -> Preferences:
		"""Return the stored preferences as they currently stand.

		Returns:
			Preferences: The values last read or written.
		"""
		return self._preferences

	@property
	def sign_in_message(self) -> str:
		"""Return what to say about the sign-in, empty when there is nothing to say.

		Returns:
			str: An instruction or a refusal, empty when the sign-in is in order.
		"""
		return self._sign_in_message

	@property
	def sign_in_link(self) -> str:
		"""Return the address a sign-in under way is waiting at.

		Returns:
			str: The address, empty when no sign-in is waiting.
		"""
		return self._sign_in_link

	@property
	def signed_in(self) -> bool:
		"""Return whether a sign-in is stored for this service.

		Returns:
			bool: True when there are tokens to read with, expired or not.
		"""
		return credentials.load(self._provider.key) is not None

	@property
	def signing_in(self) -> bool:
		"""Return whether a browser sign-in is under way.

		Returns:
			bool: True from the moment the sign-in starts until it ends.
		"""
		return self._signing_in

	@property
	def refreshing(self) -> bool:
		"""Return whether a reading is in flight.

		Returns:
			bool: True between the start of an attempt and its outcome.
		"""
		return self._refreshing

	def account(self) -> tuple[str, bool]:
		"""Return who is signed in, and whether anyone is.

		Returns:
			tuple[str, bool]: The account as the settings should name them, empty
			when the sign-in reported no name, and whether there is a sign-in at
			all.
		"""
		tokens = credentials.load(self._provider.key)
		return (tokens.account if tokens is not None else "", tokens is not None)

	def view(self) -> ProviderView:
		"""Return everything the panel draws for this service, as it stands now.

		Returns:
			ProviderView: The state, read once so a redraw sees one moment.
		"""
		account, signed_in = self.account()
		return ProviderView(
			provider=self._provider,
			snapshot=self._snapshot,
			status=self.status_text(),
			sign_in_message=self._sign_in_message,
			sign_in_link=self._sign_in_link,
			refreshing=self._refreshing,
			signed_in=signed_in,
			signing_in=self._signing_in,
			account=account,
			groups=self.metric_groups(),
			displayed=frozenset(self.displayed_keys()),
		)

	def displayed_keys(self) -> tuple[str, ...]:
		"""Return the selected keys the current reading still reports.

		A scoped limit disappears once its window empties, and a product only
		appears once it has been used, so the selection is filtered against what
		the reading actually carries.

		Returns:
			tuple of str: The keys to draw a surface for, in selection order.
			Empty before the first reading, and empty when none of the chosen
			usages is reported or none was chosen: the FORL icon then stands in,
			so no usage has to be kept to reach the widget from.
		"""
		if self._snapshot is None:
			return ()
		available = {metric.key for metric in self._snapshot.metrics()}
		return tuple(key for key in self._selected if key in available)

	def readings(self) -> tuple[MetricReading, ...]:
		"""Return one entry per surface the widget should currently show.

		Returns:
			tuple of MetricReading: The chosen usages with their percentages and
			hover text. Before the first reading, one entry carrying no reading
			per chosen usage, so the icons are in place when it arrives. Empty
			when nobody is signed in to this service or no usage is chosen.
		"""
		if not self.signed_in:
			return ()
		if self._snapshot is None:
			waiting = self._sign_in_message or f"{self._provider.label} usage: {LOADING_TEXT}"
			return tuple(MetricReading(key=key, percent=None, tooltip=waiting) for key in self._selected)
		metrics = {metric.key: metric for metric in self._snapshot.metrics()}
		return tuple(
			MetricReading(key=key, percent=metrics[key].percent, tooltip=self.tooltip(key))
			for key in self.displayed_keys()
			if key in metrics
		)

	def tooltip(self, key: str) -> str:
		"""Return the hover text for one surface: its reading and which limit it is.

		Hovering is a question about the limit, not about the widget, so a failed
		attempt does not change the answer. The exception is a sign-in that has
		run out, which takes the text because until it is fixed there is no
		answer to give.

		Args:
			key: Key of the usage the surface shows. str, non-empty.

		Returns:
			str: Text such as "34% - Current session".
		"""
		require_non_empty_str(key, "key")
		if self._sign_in_message:
			return self._sign_in_message
		metric = self._snapshot.metric(key) if self._snapshot is not None else None
		if metric is None:
			return f"{self._provider.label} usage: {LOADING_TEXT}"
		return format_icon_tooltip(metric.percent, metric.label, metric.resets_at)

	def seconds_to_next_update(self) -> float:
		"""Return how long is left before the next reading is taken.

		Returns:
			float: Seconds remaining, 0 once the reading is due and 0 when there
			has never been one.
		"""
		if self._snapshot is None:
			return 0.0
		elapsed = (now_utc() - self._snapshot.fetched_at).total_seconds()
		return max(0.0, self._poll_seconds - elapsed)

	def status_text(self) -> str:
		"""Return the line describing how fresh the reading is.

		A failure the user can do something about, which means signing in again,
		is the one thing worth saying and it takes the line. A failure they
		cannot, such as a busy endpoint, is not reported at all: the reading on
		screen is still the last good one and its age says the rest.

		Returns:
			str: The sign-in instruction when there is one, otherwise the
			countdown to the next reading, "Loading" before the first one, or
			"Not signed in" when there is no sign-in to read with.
		"""
		if self._sign_in_message:
			return self._sign_in_message
		if self._snapshot is None:
			return LOADING_TEXT if self.signed_in else NOT_SIGNED_IN_TEXT
		return format_next_update(self.seconds_to_next_update())

	def metric_groups(self) -> tuple[tuple[Metric, ...], ...]:
		"""Return every usage the reading reports, grouped as the panel groups them.

		This is what the Show section of the settings lists, in the order the
		panel draws the readings.

		Returns:
			tuple of tuple of Metric: The limits, then the products, leaving out a
			group that is empty. Empty before the first reading.
		"""
		if self._snapshot is None:
			return ()
		groups = []
		for group in (LIMIT_GROUP, PRODUCT_GROUP):
			entries = tuple(metric for metric in self._snapshot.metrics() if metric.group == group)
			if entries:
				groups.append(entries)
		return tuple(groups)

	def toggle_metric(self, key: str) -> None:
		"""Add a usage to the small surfaces, or take it away.

		Every usage can be taken away, the last one included: when no usage icon
		is left, the FORL icon takes their place, so the widget can always be
		reached.

		Args:
			key: Key of the usage the user clicked. str, non-empty.

		Returns:
			None.
		"""
		require_non_empty_str(key, "key")
		if key in self._selected:
			self._selected = tuple(other for other in self._selected if other != key)
		else:
			self._selected = self._selected + (key,)
		self.store(replace(self._preferences, views=self._selected))

	def store(self, preferences: Preferences) -> None:
		"""Keep a set of preferences, write it to disk and report the change.

		Args:
			preferences: The values to keep. Preferences.

		Returns:
			None. A file that cannot be written costs the user the choice at the
			next launch and nothing in this one, so it is not reported.
		"""
		require_type(preferences, Preferences, "preferences")
		self._preferences = preferences
		save_preferences(self._provider.key, preferences)
		self._on_change()

	def sign_in_now(self) -> None:
		"""Sign in through the browser, on a thread of its own.

		Returns:
			None. Does nothing while a sign-in is already under way.
		"""
		if self._signing_in:
			return
		self._signing_in = True
		self._signed_out = False
		self._sign_in_message = SIGNING_IN_TEXT
		self._on_change()
		threading.Thread(
			target=self._run_sign_in,
			name=f"forl-sign-in-{self._provider.key}",
			daemon=True,
		).start()

	def sign_out(self) -> None:
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
		self._sign_in_link = ""
		self._on_change()

	def open_sign_in_link(self) -> None:
		"""Open the address a sign-in is waiting at, if a browser can be opened.

		Returns:
			None. Does nothing when no sign-in is waiting.
		"""
		if not self._sign_in_link:
			return
		webbrowser.open(self._sign_in_link)

	def start(self) -> None:
		"""Start polling.

		A service with nothing stored is polled all the same: the reading fails
		before any request is made, and a sign-in completed later is picked up at
		the next reading rather than by restarting anything.

		Returns:
			None.
		"""
		self._poller.start()

	def stop(self) -> None:
		"""Stop polling and wait briefly for the worker to finish.

		Returns:
			None.
		"""
		self._poller.stop()

	def _begin_poll(self) -> None:
		"""Mark a reading as in flight and report the change.

		Returns:
			None. Runs on the interface thread.
		"""
		self._refreshing = True
		self._on_change()

	def _apply_result(self, result: PollResult) -> None:
		"""Store a reading and report the change.

		A failed attempt keeps the previous snapshot in place. Only one the user
		can fix, by signing in again, is reported; a brief network problem
		neither blanks the surfaces nor puts a message in front of them.

		Args:
			result: The outcome of one polling attempt. PollResult.

		Returns:
			None. Runs on the interface thread.
		"""
		require_type(result, PollResult, "result")
		self._refreshing = False
		# Only a failure the user can act on is kept. Anything else is dropped:
		# the reading on screen is still the last good one, and how old it is
		# says the rest. A sign-in the user is in the middle of, has just stepped
		# out of, or has never made, keeps the line: each says more than the
		# reading's complaint that there is no sign-in to read with.
		if not self._signing_in and not self._signed_out and self.signed_in:
			self._sign_in_message = result.error if result.needs_sign_in and result.error else ""
		if result.ok:
			self._snapshot = result.snapshot
		self._prompt_sign_in()
		self._on_change()

	def _prompt_sign_in(self) -> None:
		"""Put the user in front of the sign-in when a stored one has run out.

		Started once for each spell of being signed out rather than at every
		reading, so a sign-in left undone does not raise a browser window a
		minute. Never after the user signed out on purpose, and never for a
		service with nothing stored, which the user signs in to from the panel.

		Returns:
			None.
		"""
		if not self._sign_in_message:
			self._sign_in_prompted = False
			return
		if self._sign_in_prompted or self._signed_out or not self.signed_in:
			return
		self._sign_in_prompted = True
		self.sign_in_now()

	def _run_sign_in(self) -> None:
		"""Run the provider's sign-in and report the outcome to the interface thread.

		Returns:
			None. Runs on the sign-in thread.
		"""
		message = ""
		try:
			self._provider.sign_in(self._offer_address)
		except (CredentialsError, UsageRequestError) as exc:
			message = str(exc)
		self._dispatch(lambda: self._finish_sign_in(message))

	def _offer_address(self, address: str, opened: bool) -> None:
		"""Take the sign-in address from the sign-in thread to the interface thread.

		Args:
			address: Where the sign-in is waiting. str.
			opened: Whether a browser was opened at it. bool.

		Returns:
			None. Runs on the sign-in thread.
		"""
		self._dispatch(lambda: self._show_address(address, opened))

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
			None. Runs on the interface thread.
		"""
		require_type(address, str, "address")
		require_type(opened, bool, "opened")
		self._sign_in_link = address
		self._sign_in_message = SIGNING_IN_TEXT if opened else NO_BROWSER_TEXT
		self._on_change()

	def _finish_sign_in(self, message: str) -> None:
		"""Act on the outcome of a sign-in.

		Args:
			message: What went wrong, empty when nothing did. str.

		Returns:
			None. Runs on the interface thread.
		"""
		require_type(message, str, "message")
		self._signing_in = False
		self._sign_in_message = message
		self._sign_in_link = ""
		if not message:
			# The reading on screen, if there is one, belongs to whoever was
			# signed in before, so it goes rather than stands under the new name.
			self._snapshot = None
			self._poller.refresh()
		self._on_change()
