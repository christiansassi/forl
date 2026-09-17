"""The progress bar the panel is built from.

A bar is the shared rounded fill at its fullest radius, which is what gives the
ends their capsule shape where the round line caps of the Tk canvas would come
out as blunt stair steps.

The track is rendered once. The fill is re-rendered only when its width changes
by a whole device pixel, so an animating bar redraws a few dozen times rather
than at every frame.
"""

from __future__ import annotations

import tkinter as tk

from PIL import Image, ImageTk

from ..render.shapes import rounded_fill
from ..validation import require_non_empty_str, require_number_in_range, require_type


def render_capsule(width: int, height: int, color: str) -> Image.Image:
	"""Render a fully rounded horizontal bar as an RGBA image.

	Args:
		width: Width of the bar in pixels. int, 1 or more.
		height: Height of the bar in pixels. int, 1 or more.
		color: Fill color as a "#rrggbb" string. str, non-empty.

	Returns:
		PIL.Image.Image: The bar, mode "RGBA", on a transparent background.
	"""
	height = max(1, int(height))
	return rounded_fill(width, height, color, height / 2.0)


class CapsuleBar:
	"""A fully rounded progress bar whose fill can be updated every frame."""

	def __init__(
		self,
		canvas: tk.Canvas,
		box: tuple[float, float, float, float],
		track_color: str,
		fill_color: str,
		tags: str,
	) -> None:
		"""Draw the track and an empty fill on a canvas.

		Args:
			canvas: The canvas to draw on. tkinter.Canvas.
			box: The full bar as (left, top, right, bottom) in pixels. tuple of
				four floats.
			track_color: Color of the unfilled part as a "#rrggbb" string. str.
			fill_color: Color of the filled part as a "#rrggbb" string. str.
			tags: Tag to attach to both items of the bar. str, non-empty.

		Returns:
			None.
		"""
		require_type(canvas, tk.Canvas, "canvas")
		require_non_empty_str(track_color, "track_color")
		require_non_empty_str(fill_color, "fill_color")
		require_non_empty_str(tags, "tags")

		left, top, right, bottom = box
		self._canvas = canvas
		self._left = int(round(left))
		self._top = int(round(top))
		self._width = max(1, int(round(right - left)))
		self._height = max(1, int(round(bottom - top)))
		self._fill_color = fill_color
		self._filled_width = 0

		self._track_photo = ImageTk.PhotoImage(render_capsule(self._width, self._height, track_color))
		canvas.create_image(self._left, self._top, image=self._track_photo, anchor="nw", tags=tags)
		self._fill_photo: ImageTk.PhotoImage | None = None
		self._fill_item = canvas.create_image(self._left, self._top, anchor="nw", tags=tags, state="hidden")

	def set_fraction(self, fraction: float) -> None:
		"""Resize the filled part of the bar.

		An empty bar hides its fill; a fill shorter than the bar is round is
		drawn as the round end alone, so a small reading still shows something.

		Args:
			fraction: Share of the bar to fill, 0 to 1. float.

		Returns:
			None.
		"""
		require_number_in_range(fraction, 0.0, 1.0, "fraction")
		if fraction <= 0.0:
			self._filled_width = 0
			self._canvas.itemconfigure(self._fill_item, state="hidden")
			return

		wanted = max(self._height, min(self._width, int(round(self._width * fraction))))
		if wanted == self._filled_width:
			return
		self._filled_width = wanted
		self._fill_photo = ImageTk.PhotoImage(render_capsule(wanted, self._height, self._fill_color))
		self._canvas.itemconfigure(self._fill_item, image=self._fill_photo, state="normal")
