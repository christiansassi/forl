"""Spring driven animation for the panel.

Motion here is described the way Apple describes it, with a damping ratio and a
response time rather than a duration and an easing curve. A spring animates from
wherever the value currently is, so retargeting it mid flight is continuous
instead of a jump, and a value never has to wait for a previous animation to
finish before it can be redirected. The bars of the panel are what this drives.
"""

from __future__ import annotations

import math
import tkinter as tk
from typing import Callable

from ..validation import require_number_in_range, require_type

FRAME_INTERVAL_MS = 16
SETTLE_VALUE_EPSILON = 0.001
SETTLE_VELOCITY_EPSILON = 0.01

DEFAULT_RESPONSE = 0.4
DEFAULT_DAMPING = 1.0


class Spring:
	"""A single scalar value that moves toward a target under spring forces."""

	def __init__(self, value: float, response: float = DEFAULT_RESPONSE, damping: float = DEFAULT_DAMPING) -> None:
		"""Create a spring resting at a value.

		Args:
			value: Starting value, which is also the initial target. float.
			response: Time the value takes to reach the target, in seconds. This
				is not a duration; the settle time follows from it and from the
				damping. float, between 0.05 and 5.
			damping: Damping ratio. 1.0 settles without overshoot, below 1.0
				overshoots and bounces. float, between 0.1 and 2.

		Returns:
			None.
		"""
		require_type(value, (int, float), "value")
		require_number_in_range(response, 0.05, 5.0, "response")
		require_number_in_range(damping, 0.1, 2.0, "damping")

		self.value = float(value)
		self.target = float(value)
		self.velocity = 0.0
		self._angular_frequency = 2.0 * math.pi / response
		self._damping = damping

	def set_target(self, target: float, velocity: float | None = None) -> None:
		"""Point the spring at a new target without disturbing its current value.

		Args:
			target: The value to move toward. float.
			velocity: Velocity to carry into the new motion in units per second,
				or None to keep the velocity the spring already has. float or None.

		Returns:
			None.
		"""
		require_type(target, (int, float), "target")
		self.target = float(target)
		if velocity is not None:
			require_type(velocity, (int, float), "velocity")
			self.velocity = float(velocity)

	def jump_to(self, value: float) -> None:
		"""Move the spring to a value at once, cancelling any motion.

		Used when the user has turned animation off, and when a panel is shown
		again after being hidden.

		Args:
			value: The value to take. float.

		Returns:
			None.
		"""
		require_type(value, (int, float), "value")
		self.value = float(value)
		self.target = float(value)
		self.velocity = 0.0

	def rewind(self, value: float) -> None:
		"""Move the spring to a value while leaving its target alone.

		This is what replays an entrance: the bars are put back at empty and then
		travel to the targets the layout already gave them.

		Args:
			value: The value to take. float.

		Returns:
			None.
		"""
		require_type(value, (int, float), "value")
		self.value = float(value)
		self.velocity = 0.0

	def step(self, dt: float) -> float:
		"""Advance the spring by one frame and return the new value.

		Args:
			dt: Length of the frame in seconds. float, between 0 and 0.1.

		Returns:
			float: The value after the step.
		"""
		require_number_in_range(dt, 0.0, 0.1, "dt")
		if self.settled:
			self.value = self.target
			self.velocity = 0.0
			return self.value

		offset = self.value - self.target
		acceleration = -2.0 * self._damping * self._angular_frequency * self.velocity
		acceleration -= self._angular_frequency * self._angular_frequency * offset
		self.velocity += acceleration * dt
		self.value += self.velocity * dt
		return self.value

	@property
	def settled(self) -> bool:
		"""Return whether the spring has come to rest at its target.

		Returns:
			bool: True when both the remaining distance and the velocity are
			below the settling thresholds.
		"""
		return abs(self.value - self.target) < SETTLE_VALUE_EPSILON and abs(self.velocity) < SETTLE_VELOCITY_EPSILON


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
