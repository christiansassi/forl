"""The slider the settings view picks a number of minutes with.

A slider is rendered by Pillow and placed on the Tk canvas as an image, as the
switch is, because the Tk canvas draws without antialiasing and its knob would
come out as a polygon. It holds whole values between two ends and reports which
one a point along it stands for, so the panel can follow a drag without knowing
how the slider is drawn. The values it holds can be spaced by a step, and a
drag lands on the nearest one.
"""

from __future__ import annotations

import tkinter as tk

from PIL import ImageTk

from ..render.shapes import render_slider
from ..validation import require_int_in_range, require_non_empty_str, require_number_in_range, require_type


class Slider:
	"""A slider over a range of whole numbers, redrawn in place as its value changes."""

	def __init__(
		self,
		canvas: tk.Canvas,
		box: tuple[float, float, float, float],
		maximum: int,
		step: int,
		colors: tuple[str, str, str],
		tags: str,
	) -> None:
		"""Draw a slider on a canvas, with its knob at the left hand end.

		Args:
			canvas: The canvas to draw on. tkinter.Canvas.
			box: The slider as (left, top, right, bottom) in pixels; its height
				is the size of the knob. tuple of four floats.
			maximum: The value at the right hand end; the left hand end is 0.
				int, greater than 0.
			step: The spacing of the values the slider holds. int, greater than
				0, dividing maximum evenly.
			colors: The track past the knob, the track before it and the dot in
				the knob, and the ring around the dot, each a "#rrggbb" string.
				tuple of three str.
			tags: Tag to attach to the image. str, non-empty.

		Returns:
			None.
		"""
		require_type(canvas, tk.Canvas, "canvas")
		require_int_in_range(maximum, 1, 10_000, "maximum")
		require_int_in_range(step, 1, maximum, "step")
		if maximum % step:
			raise ValueError(f"step must divide maximum evenly, got {step} for {maximum}")
		require_type(colors, tuple, "colors")
		if len(colors) != 3:
			raise ValueError(f"colors must hold 3 colors, got {len(colors)}")
		for color in colors:
			require_non_empty_str(color, "colors")
		require_non_empty_str(tags, "tags")

		left, top, right, bottom = box
		self._canvas = canvas
		self._left = int(round(left))
		self._top = int(round(top))
		self._width = max(1, int(round(right - left)))
		self._height = max(1, int(round(bottom - top)))
		self._maximum = maximum
		self._step = step
		self._colors = colors
		self._photo: ImageTk.PhotoImage | None = None
		# Nothing has been drawn yet, so no value counts as already showing.
		self._drawn = -1

		self._item = canvas.create_image(self._left, self._top, anchor="nw", tags=tags)
		self.set_value(0)

	@property
	def box(self) -> tuple[int, int, int, int]:
		"""Return where the slider was drawn.

		Returns:
			tuple[int, int, int, int]: The slider as (left, top, right, bottom)
			in device pixels, as it stands with the content at the top of its
			scroll.
		"""
		return (self._left, self._top, self._left + self._width, self._top + self._height)

	def value_at(self, x: float) -> int:
		"""Return the value a point along the slider stands for.

		The knob's center travels from half a knob in at one end to half a knob
		in at the other, so those are the points that stand for the two ends.

		Args:
			x: Position across the canvas in device pixels. float.

		Returns:
			int: The nearest value on the step, clamped to the range of the
			slider.
		"""
		require_number_in_range(x, -1e9, 1e9, "x")
		travel = max(1, self._width - self._height)
		fraction = (x - self._left - self._height / 2.0) / travel
		steps = self._maximum // self._step
		return int(round(min(1.0, max(0.0, fraction)) * steps)) * self._step

	def set_value(self, value: int) -> None:
		"""Move the knob to a value.

		Args:
			value: The value to show. int, 0 to the maximum, on the step.

		Returns:
			None.
		"""
		require_int_in_range(value, 0, self._maximum, "value")
		if value % self._step:
			raise ValueError(f"value must be a multiple of {self._step}, got {value}")
		if value == self._drawn:
			return
		self._drawn = value
		track, fill, ring = self._colors
		self._photo = ImageTk.PhotoImage(
			render_slider(self._width, self._height, value / self._maximum, track, fill, ring)
		)
		self._canvas.itemconfigure(self._item, image=self._photo)
