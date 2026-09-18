"""Rounded fills, drawn by Pillow rather than by the Tk canvas.

The Tk canvas draws without antialiasing, so a rounded corner it draws comes out
as a stair step at the sizes this interface uses. Every rounded shape is
therefore rendered here on a supersampled canvas, reduced, and placed on the
canvas as an image.

The bars of the panel, the highlight behind a menu row and the track of a switch
are the same rounded rectangle at three different radii, so they share one
renderer.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from ..validation import require_non_empty_str, require_number_in_range, require_type
from .theme import TRANSPARENT

SUPERSAMPLE = 4

# How far the knob of a switch sits inside its track, as a share of the track
# height. The system switch leaves about this much on every side.
KNOB_INSET_RATIO = 0.085


def rounded_fill(width: int, height: int, color: str, radius: float) -> Image.Image:
	"""Render a filled rounded rectangle as an RGBA image.

	Args:
		width: Width in pixels. int, 1 or more after rounding.
		height: Height in pixels. int, 1 or more after rounding.
		color: Fill color as a "#rrggbb" string. str, non-empty.
		radius: Corner radius in pixels. Larger than half the shorter side gives
			a capsule. float, 0 or more.

	Returns:
		PIL.Image.Image: The shape, mode "RGBA", on a transparent background.
	"""
	require_non_empty_str(color, "color")
	require_type(radius, (int, float), "radius")

	width = max(1, int(round(width)))
	height = max(1, int(round(height)))
	image = Image.new("RGBA", (width * SUPERSAMPLE, height * SUPERSAMPLE), TRANSPARENT)
	ImageDraw.Draw(image).rounded_rectangle(
		(0, 0, width * SUPERSAMPLE - 1, height * SUPERSAMPLE - 1),
		radius=max(0.0, float(radius)) * SUPERSAMPLE,
		fill=color,
	)
	return image.resize((width, height), Image.LANCZOS)


def render_switch(width: int, height: int, fraction: float, track_color: str, knob_color: str) -> Image.Image:
	"""Render a switch as an RGBA image, with its knob anywhere along the track.

	The knob is placed by fraction rather than by a flag so the switch can be
	animated. Its colors are given already blended, because how far through the
	change they are is the caller's business and not this renderer's.

	Args:
		width: Width of the track in pixels. int, 1 or more after rounding.
		height: Height of the track in pixels, which also sets the size of the
			knob. int, 1 or more after rounding.
		fraction: How far the knob has travelled, 0 at the left hand end and 1 at
			the right. float, 0 to 1.
		track_color: Color of the track as a "#rrggbb" string. str, non-empty.
		knob_color: Color of the knob as a "#rrggbb" string. str, non-empty.

	Returns:
		PIL.Image.Image: The switch, mode "RGBA", on a transparent background.
	"""
	require_number_in_range(fraction, 0.0, 1.0, "fraction")
	require_non_empty_str(track_color, "track_color")
	require_non_empty_str(knob_color, "knob_color")

	width = max(1, int(round(width)))
	height = max(1, int(round(height)))
	scale = SUPERSAMPLE
	image = Image.new("RGBA", (width * scale, height * scale), TRANSPARENT)
	draw = ImageDraw.Draw(image)
	draw.rounded_rectangle(
		(0, 0, width * scale - 1, height * scale - 1),
		radius=height * scale / 2.0,
		fill=track_color,
	)

	inset = height * scale * KNOB_INSET_RATIO
	diameter = height * scale - 2 * inset
	travel = width * scale - 2 * inset - diameter
	left = inset + travel * fraction
	draw.ellipse((left, inset, left + diameter, inset + diameter), fill=knob_color)
	return image.resize((width, height), Image.LANCZOS)
