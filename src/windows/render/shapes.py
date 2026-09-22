"""Rounded fills, drawn by Pillow rather than by the Tk canvas.

The Tk canvas draws without antialiasing, so a rounded corner it draws comes out
as a stair step at the sizes this interface uses. Every rounded shape is
therefore rendered here on a supersampled canvas, reduced, and placed on the
canvas as an image.

The bars of the panel, the highlight behind a menu row and the track of a switch
are the same rounded rectangle at three different radii, so they share one
renderer. The tabs and the checkboxes add a border to it, and the slider is a
thin capsule with a round knob on it.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from ..validation import require_non_empty_str, require_number_in_range, require_type
from .theme import TRANSPARENT

SUPERSAMPLE = 4

# How far the knob of a switch sits inside its track, as a share of the track
# height. The system switch leaves about this much on every side.
KNOB_INSET_RATIO = 0.085

# Corner radius and border of a checkbox, and the weight of its check, as shares
# of its size.
CHECKBOX_RADIUS_RATIO = 0.22
CHECKBOX_STROKE_RATIO = 0.08
CHECK_STROKE_RATIO = 0.13

# The track of a slider and the dot at the middle of its knob, as shares of the
# knob, which is as tall as the slider. The system slider is drawn this way: a
# ring in the surface color around a dot in the accent.
SLIDER_TRACK_RATIO = 0.2
SLIDER_DOT_RATIO = 0.55


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


def outlined_fill(width: int, height: int, fill: str, outline: str, radius: float, stroke: float) -> Image.Image:
	"""Render a filled rounded rectangle with a border, as an RGBA image.

	The border is drawn inside the shape rather than centered on its edge, so the
	image is exactly the size asked for and two of them laid side by side do not
	overlap.

	Args:
		width: Width in pixels. int, 1 or more after rounding.
		height: Height in pixels. int, 1 or more after rounding.
		fill: Color inside the border as a "#rrggbb" string. str, non-empty.
		outline: Color of the border as a "#rrggbb" string. str, non-empty.
		radius: Corner radius of the outer edge in pixels. float, 0 or more.
		stroke: Thickness of the border in pixels. float, 0 or more.

	Returns:
		PIL.Image.Image: The shape, mode "RGBA", on a transparent background.
	"""
	require_non_empty_str(fill, "fill")
	require_non_empty_str(outline, "outline")
	require_type(radius, (int, float), "radius")
	require_type(stroke, (int, float), "stroke")

	width = max(1, int(round(width)))
	height = max(1, int(round(height)))
	scale = SUPERSAMPLE
	image = Image.new("RGBA", (width * scale, height * scale), TRANSPARENT)
	ImageDraw.Draw(image).rounded_rectangle(
		(0, 0, width * scale - 1, height * scale - 1),
		radius=max(0.0, float(radius)) * scale,
		fill=fill,
		outline=outline,
		width=max(1, int(round(max(0.0, float(stroke)) * scale))),
	)
	return image.resize((width, height), Image.LANCZOS)


def render_checkbox(size: int, checked: bool, accent: str, mark: str, surface: str, border: str) -> Image.Image:
	"""Render a checkbox as an RGBA image, the way the Mac app's checkboxes look.

	A checked box is filled with the accent and carries a check mark; an
	unchecked one is an empty rounded square with a thin border.

	Args:
		size: Width and height in pixels. int, 1 or more after rounding.
		checked: Whether the box is checked. bool.
		accent: Fill of a checked box as a "#rrggbb" string. str, non-empty.
		mark: Color of the check mark, which has to read on the accent, as a
			"#rrggbb" string. str, non-empty.
		surface: Fill of an unchecked box, which is the color it sits on, as a
			"#rrggbb" string. str, non-empty.
		border: Border of an unchecked box as a "#rrggbb" string. str, non-empty.

	Returns:
		PIL.Image.Image: The checkbox, mode "RGBA", on a transparent background.
	"""
	require_type(checked, bool, "checked")
	for name, color in (("accent", accent), ("mark", mark), ("surface", surface), ("border", border)):
		require_non_empty_str(color, name)

	size = max(1, int(round(size)))
	radius = size * CHECKBOX_RADIUS_RATIO
	if not checked:
		return outlined_fill(size, size, surface, border, radius, max(1.0, size * CHECKBOX_STROKE_RATIO))

	scale = SUPERSAMPLE
	edge = size * scale
	image = Image.new("RGBA", (edge, edge), TRANSPARENT)
	draw = ImageDraw.Draw(image)
	draw.rounded_rectangle((0, 0, edge - 1, edge - 1), radius=radius * scale, fill=accent)
	# The check is a short stroke down and a long one up, placed by shares of the
	# box so it stays in proportion at any size.
	points = [(edge * 0.27, edge * 0.52), (edge * 0.43, edge * 0.68), (edge * 0.74, edge * 0.34)]
	draw.line(points, fill=mark, width=max(1, int(round(edge * CHECK_STROKE_RATIO))), joint="curve")
	return image.resize((size, size), Image.LANCZOS)


def render_slider(
	width: int,
	height: int,
	fraction: float,
	track_color: str,
	fill_color: str,
	ring_color: str,
) -> Image.Image:
	"""Render a slider as an RGBA image, with its knob anywhere along the track.

	The track is filled in the accent up to the knob and left plain after it,
	and the knob is a ring around a dot in the accent, as the system slider is.

	Args:
		width: Width of the slider in pixels. int, 1 or more after rounding.
		height: Height of the slider in pixels, which is the size of the knob.
			int, 1 or more after rounding.
		fraction: Where the knob sits, 0 at the left hand end and 1 at the
			right. float, 0 to 1.
		track_color: Color of the track past the knob as a "#rrggbb" string.
			str, non-empty.
		fill_color: Color of the track before the knob, and of the dot in the
			knob, as a "#rrggbb" string. str, non-empty.
		ring_color: Color of the ring around the dot as a "#rrggbb" string. str,
			non-empty.

	Returns:
		PIL.Image.Image: The slider, mode "RGBA", on a transparent background.
	"""
	require_number_in_range(fraction, 0.0, 1.0, "fraction")
	require_non_empty_str(track_color, "track_color")
	require_non_empty_str(fill_color, "fill_color")
	require_non_empty_str(ring_color, "ring_color")

	width = max(1, int(round(width)))
	height = max(1, int(round(height)))
	scale = SUPERSAMPLE
	image = Image.new("RGBA", (width * scale, height * scale), TRANSPARENT)
	draw = ImageDraw.Draw(image)

	diameter = height * scale
	track = max(1.0, diameter * SLIDER_TRACK_RATIO)
	middle = diameter / 2.0
	# The knob's center travels between the two ends of the track, so the knob
	# never hangs over either edge of the image.
	center = middle + (width * scale - diameter) * fraction
	top, bottom = middle - track / 2.0, middle + track / 2.0
	# The track runs from edge to edge, so its ends line up with the text and
	# the controls above it; the knob, whose center stops half a knob in, covers
	# whichever end it is at.
	draw.rounded_rectangle((0, top, width * scale - 1, bottom), radius=track / 2.0, fill=track_color)
	draw.rounded_rectangle((0, top, center, bottom), radius=track / 2.0, fill=fill_color)
	draw.ellipse((center - middle, 0, center + middle - 1, diameter - 1), fill=ring_color)
	dot = diameter * SLIDER_DOT_RATIO / 2.0
	draw.ellipse((center - dot, middle - dot, center + dot, middle + dot), fill=fill_color)
	return image.resize((width, height), Image.LANCZOS)
