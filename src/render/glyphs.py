"""The two interface marks, built from geometry rather than read from a file.

The provider marks are brand artwork and ship as SVG, but the gear that opens
the settings and the chevron that leaves them are plain shapes that are shorter
to describe than to store: a gear is a disc with teeth around it and a hole
through the middle, and a chevron is two strokes meeting at a point. Describing
them here also means they come out at exactly the size asked for, with no path
to parse and no file to find.

Both are drawn supersampled and reduced, the way every other rounded shape in
the interface is, and both are cached, because the panel asks for the same mark
at the same size every time it is rebuilt.
"""

from __future__ import annotations

import math
from functools import lru_cache

from PIL import Image, ImageDraw

from ..validation import require_non_empty_str, require_positive_int
from .theme import TRANSPARENT

SUPERSAMPLE = 8

TEETH = 8

# Radii as shares of the full size. The teeth reach the edge, the body sits
# inside them, and the hole is the gap that makes the shape read as a gear
# rather than as a cog wheel silhouette.
OUTER_RADIUS_RATIO = 0.5
BODY_RADIUS_RATIO = 0.35
HOLE_RADIUS_RATIO = 0.15

# Angular half width of a tooth at its tip and at its root, as shares of the
# half pitch. A tooth narrower at the tip than at the root is what gives the
# gear its draft rather than leaving it a star.
TIP_HALF_WIDTH = 0.44
ROOT_HALF_WIDTH = 0.72

# Chevron proportions. It is drawn tight to its own ink rather than centered on
# a square, so a caller placing it at the text margin gets a mark whose stroke
# starts there, instead of one indented by the empty part of a square. Width is
# a share of the height, and the stroke with it: the stroke is set to the weight
# of the gear's teeth, so the two marks read as one set.
CHEVRON_ASPECT = 0.62
CHEVRON_STROKE_RATIO = 0.16


def _point(center: float, radius: float, angle: float) -> tuple[float, float]:
	"""Return a point at a radius and angle from a center.

	Args:
		center: The center coordinate, the same across and down. float.
		radius: Distance from the center in pixels. float.
		angle: Direction in radians, measured from the positive x axis. float.

	Returns:
		tuple[float, float]: The point as (x, y).
	"""
	return (center + radius * math.cos(angle), center + radius * math.sin(angle))


@lru_cache(maxsize=32)
def render_gear(size: int, color: str) -> Image.Image:
	"""Render the settings gear as a square RGBA image.

	Args:
		size: Width and height in pixels. int, greater than 0.
		color: Fill color as a "#rrggbb" string. str, non-empty.

	Returns:
		PIL.Image.Image: The gear, mode "RGBA", on a transparent background.
	"""
	require_positive_int(size, "size")
	require_non_empty_str(color, "color")

	edge = size * SUPERSAMPLE
	image = Image.new("RGBA", (edge, edge), TRANSPARENT)
	draw = ImageDraw.Draw(image)

	center = edge / 2.0
	outer = edge * OUTER_RADIUS_RATIO
	body = edge * BODY_RADIUS_RATIO
	half_pitch = math.pi / TEETH
	for index in range(TEETH):
		middle = index * 2.0 * half_pitch
		# The root of a tooth is drawn inside the body so the two shapes merge
		# without a seam where they meet.
		draw.polygon(
			[
				_point(center, body * 0.9, middle - half_pitch * ROOT_HALF_WIDTH),
				_point(center, outer, middle - half_pitch * TIP_HALF_WIDTH),
				_point(center, outer, middle + half_pitch * TIP_HALF_WIDTH),
				_point(center, body * 0.9, middle + half_pitch * ROOT_HALF_WIDTH),
			],
			fill=color,
		)
	draw.ellipse((center - body, center - body, center + body, center + body), fill=color)

	hole = edge * HOLE_RADIUS_RATIO
	# Drawing writes pixels rather than blending them, so a fully transparent
	# fill cuts the hole out of what is already there.
	draw.ellipse((center - hole, center - hole, center + hole, center + hole), fill=TRANSPARENT)
	return image.resize((size, size), Image.LANCZOS)


@lru_cache(maxsize=32)
def render_back(size: int, color: str) -> Image.Image:
	"""Render the back chevron as an RGBA image, pointing left.

	The image is only as wide as the chevron itself, so its stroke lines up with
	the left edge of whatever it is placed against.

	Args:
		size: Height in pixels. The width follows from it. int, greater than 0.
		color: Stroke color as a "#rrggbb" string. str, non-empty.

	Returns:
		PIL.Image.Image: The chevron, mode "RGBA", on a transparent background,
		size pixels tall and narrower than it is tall.
	"""
	require_positive_int(size, "size")
	require_non_empty_str(color, "color")

	height = size * SUPERSAMPLE
	width = max(1, int(round(height * CHEVRON_ASPECT)))
	image = Image.new("RGBA", (width, height), TRANSPARENT)
	draw = ImageDraw.Draw(image)

	stroke = max(1.0, height * CHEVRON_STROKE_RATIO)
	radius = stroke / 2.0
	points = [
		(width - radius, radius),
		(radius, height / 2.0),
		(width - radius, height - radius),
	]
	draw.line(points, fill=color, width=int(round(stroke)), joint="curve")

	# The line is drawn with square ends, so the two tips are rounded off by
	# hand to match the rounded joint at the point of the chevron.
	for x, y in (points[0], points[2]):
		draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
	return image.resize((max(1, int(round(size * CHEVRON_ASPECT))), size), Image.LANCZOS)
