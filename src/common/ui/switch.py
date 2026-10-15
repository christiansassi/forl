"""The switch the settings view is built from.

A switch is rendered by Pillow and placed on the Tk canvas as an image, the same
way the bars are, because the Tk canvas draws without antialiasing and a capsule
it drew would have blunt ends.

The knob is placed by a fraction of the track rather than by a flag, and the
track is colored for whatever fraction that is, so the two ends are the only
positions the panel asks for and neither end is a special case. A position
already on screen is not rendered again.
"""

from __future__ import annotations

import tkinter as tk

from PIL import ImageTk

from ..render.shapes import render_switch
from ..render.theme import mix_hex, on_accent
from ..validation import require_non_empty_str, require_number_in_range, require_type


class Switch:
	"""A switch whose knob can be moved along its track every frame."""

	def __init__(
		self,
		canvas: tk.Canvas,
		box: tuple[float, float, float, float],
		off_track: str,
		on_track: str,
		tags: str,
	) -> None:
		"""Draw a switch on a canvas, with its knob at the left hand end.

		Args:
			canvas: The canvas to draw on. tkinter.Canvas.
			box: The track as (left, top, right, bottom) in pixels. tuple of four
				floats.
			off_track: Color of the track when the switch is off, as a "#rrggbb"
				string. str, non-empty.
			on_track: Color of the track when it is on, as a "#rrggbb" string.
				str, non-empty.
			tags: Tag to attach to the image. str, non-empty.

		Returns:
			None.
		"""
		require_type(canvas, tk.Canvas, "canvas")
		require_non_empty_str(off_track, "off_track")
		require_non_empty_str(on_track, "on_track")
		require_non_empty_str(tags, "tags")

		left, top, right, bottom = box
		self._canvas = canvas
		self._left = int(round(left))
		self._top = int(round(top))
		self._width = max(1, int(round(right - left)))
		self._height = max(1, int(round(bottom - top)))
		self._off_track = off_track
		self._on_track = on_track
		self._photo: ImageTk.PhotoImage | None = None
		# Nothing has been drawn yet, so no position counts as already showing.
		self._drawn_at = -1

		self._item = canvas.create_image(self._left, self._top, anchor="nw", tags=tags)
		self.set_fraction(0.0)

	@property
	def box(self) -> tuple[int, int, int, int]:
		"""Return where the switch was drawn.

		Returns:
			tuple[int, int, int, int]: The track as (left, top, right, bottom) in
			device pixels.
		"""
		return (self._left, self._top, self._left + self._width, self._top + self._height)

	def set_fraction(self, fraction: float) -> None:
		"""Move the knob along the track and recolor the track to match.

		The knob takes its color from the track as the track is at that moment,
		rather than from a color of its own. One of the two accents is white, so
		a knob of a fixed color would disappear into one end of its own track.

		Args:
			fraction: How far across the knob sits, 0 at the left hand end and 1
				at the right. float, 0 to 1.

		Returns:
			None.
		"""
		require_number_in_range(fraction, 0.0, 1.0, "fraction")

		position = int(round(self._width * fraction))
		if position == self._drawn_at:
			return
		self._drawn_at = position

		track = mix_hex(self._off_track, self._on_track, fraction)
		self._photo = ImageTk.PhotoImage(
			render_switch(self._width, self._height, fraction, track, on_accent(track))
		)
		self._canvas.itemconfigure(self._item, image=self._photo)
