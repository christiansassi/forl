"""Take usage readings from a provider on a fixed schedule.

The poller is the only place that drives a provider. It hands every outcome,
success or failure, to a callback so the user interface can keep showing a stale
reading while a failure is noted.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from ..validation import require_positive_int, require_type
from .errors import CredentialsError, UsageAuthError, UsageRequestError
from .snapshot import UsageSnapshot, now_utc


@dataclass(frozen=True)
class PollResult:
	"""The outcome of one polling attempt.

	Attributes:
		snapshot: The reading that was fetched, or None when the attempt failed.
			UsageSnapshot or None.
		error: A message describing why the attempt failed, or None on success.
			str or None.
		needs_sign_in: Whether the failure is fixed by signing in again rather
			than by waiting. bool.
		attempted_at: When the attempt finished. datetime in UTC.
	"""

	snapshot: UsageSnapshot | None
	error: str | None
	needs_sign_in: bool
	attempted_at: datetime

	@property
	def ok(self) -> bool:
		"""Return whether the attempt produced a usage reading.

		Returns:
			bool: True when a snapshot is present.
		"""
		return self.snapshot is not None


def poll_once(read: Callable[[], UsageSnapshot]) -> PollResult:
	"""Take one reading from a provider.

	Never raises for an expected failure such as a missing login or an offline
	machine; those are reported through the returned result instead.

	Args:
		read: The reading function of a provider. Callable taking no arguments
			and returning a UsageSnapshot.

	Returns:
		PollResult: The reading, or the reason it could not be taken.
	"""
	if not callable(read):
		raise TypeError("read must be callable")

	attempted_at = now_utc()
	try:
		snapshot = read()
	except (CredentialsError, UsageAuthError) as exc:
		return PollResult(snapshot=None, error=str(exc), needs_sign_in=True, attempted_at=attempted_at)
	except UsageRequestError as exc:
		return PollResult(snapshot=None, error=str(exc), needs_sign_in=False, attempted_at=attempted_at)
	return PollResult(snapshot=snapshot, error=None, needs_sign_in=False, attempted_at=attempted_at)


class UsagePoller:
	"""Read from a provider on an interval until stopped.

	The worker sleeps on an event rather than a timer, so shutdown does not have
	to wait out the interval.
	"""

	def __init__(
		self,
		read: Callable[[], UsageSnapshot],
		on_result: Callable[[PollResult], None],
		on_begin: Callable[[], None],
		interval_seconds: int = 60,
	) -> None:
		"""Create a poller bound to a provider and its two callbacks.

		Args:
			read: The reading function of a provider. Callable taking no
				arguments and returning a UsageSnapshot.
			on_result: Called with every PollResult, from the worker thread.
				Callable taking one PollResult and returning None.
			on_begin: Called from the worker thread as each attempt starts, so the
				interface can show that a reading is in flight. Callable taking no
				arguments and returning None.
			interval_seconds: Delay between attempts. int, greater than 0.

		Returns:
			None.
		"""
		for name, callback in (("read", read), ("on_result", on_result), ("on_begin", on_begin)):
			if not callable(callback):
				raise TypeError(f"{name} must be callable")
		require_positive_int(interval_seconds, "interval_seconds")

		self._read = read
		self._on_result = on_result
		self._on_begin = on_begin
		self._interval_seconds = interval_seconds
		self._wake = threading.Event()
		self._stopped = threading.Event()
		self._thread: threading.Thread | None = None

	def start(self) -> None:
		"""Start the worker thread and take the first reading immediately.

		Returns:
			None. Calling it on a running poller does nothing.
		"""
		if self._thread is not None:
			return
		self._thread = threading.Thread(target=self._run, name="usage-poller", daemon=True)
		self._thread.start()

	def refresh(self) -> None:
		"""Take the next reading now instead of waiting out the interval.

		Used when something the reading depends on has changed under it, such as
		the sign-in being read from a different folder.

		Returns:
			None. Does nothing when the poller is not running.
		"""
		self._wake.set()

	def stop(self, timeout: float = 5.0) -> None:
		"""Stop the worker thread and wait briefly for it to finish.

		Args:
			timeout: Seconds to wait for the thread to exit. float, between 0 and 60.

		Returns:
			None.
		"""
		require_type(timeout, (int, float), "timeout")
		self._stopped.set()
		self._wake.set()
		if self._thread is not None:
			self._thread.join(timeout=max(0.0, float(timeout)))
			self._thread = None

	def _run(self) -> None:
		"""Poll until stopped, reporting every outcome to the callbacks.

		Returns:
			None.
		"""
		while not self._stopped.is_set():
			self._notify(self._on_begin)
			result = poll_once(self._read)
			if self._stopped.is_set():
				return
			self._notify(lambda: self._on_result(result))
			self._wake.wait(self._interval_seconds)
			self._wake.clear()

	@staticmethod
	def _notify(callback: Callable[[], None]) -> None:
		"""Run one consumer callback, swallowing anything it raises.

		A failing consumer must not kill the polling thread, because the next
		reading still has a chance to arrive.

		Args:
			callback: The consumer call to make. Callable taking no arguments and
				returning None.

		Returns:
			None.
		"""
		try:
			callback()
		except Exception:
			pass
