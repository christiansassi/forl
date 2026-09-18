"""Drive the panel's springs from the Tk scheduler.

Tk has no frame callback, so one is built from its timer: the ticker asks for a
frame, runs it, and asks for another for as long as the caller says it still has
something to move. The spring itself is shared with the macOS surfaces and lives
in spring.py; this module is only the clock that steps it.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable

from ..validation import require_type
from .spring import DEFAULT_DAMPING, DEFAULT_RESPONSE, Spring

FRAME_INTERVAL_MS = 16

__all__ = ["DEFAULT_DAMPING", "DEFAULT_RESPONSE", "FRAME_INTERVAL_MS", "Spring", "Ticker"]


class Ticker:
	"""Call a function once per frame while animation is in progress."""

	def __init__(self, widget: tk.Misc, on_frame: Callable[[float], bool]) -> None:
		"""Bind a per frame callback to a widget event loop.

		Args:
			widget: Any widget of the application, used for its scheduler.
				tkinter.Misc.
			on_frame: Called with the frame length in seconds; returns True while
				it wants more frames. Callable taking one float and returning bool.

		Returns:
			None.
		"""
		require_type(widget, tk.Misc, "widget")
		if not callable(on_frame):
			raise TypeError("on_frame must be callable")

		self._widget = widget
		self._on_frame = on_frame
		self._job: str | None = None

	def start(self) -> None:
		"""Begin calling the frame callback, if it is not already running.

		Returns:
			None.
		"""
		if self._job is None:
			self._job = self._widget.after(FRAME_INTERVAL_MS, self._tick)

	def stop(self) -> None:
		"""Stop calling the frame callback.

		Returns:
			None.
		"""
		if self._job is not None:
			self._widget.after_cancel(self._job)
			self._job = None

	def _tick(self) -> None:
		"""Run one frame and schedule the next one if more are wanted.

		Returns:
			None.
		"""
		self._job = None
		if self._on_frame(FRAME_INTERVAL_MS / 1000.0):
			self._job = self._widget.after(FRAME_INTERVAL_MS, self._tick)
