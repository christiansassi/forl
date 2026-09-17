"""Draw the notification area icon.

A taskbar cell is square and small, so the icon uses all of it: a rounded column
that fills from the bottom as the window is spent, with the reading across the
middle of it. The column is drawn in the color of the service being reported on,
which is what tells two widgets apart at a glance, since a cell carries no label.

The reading is white, except where white would disappear into the fill. A fill
too pale to carry white text has the reading written twice instead, light above
the level and dark below it, so it reads against the empty part of the tank and
the filled part alike. That is what a service colored white needs and a service
colored orange does not.

Drawing happens on a supersampled canvas that is reduced at the end, which keeps
the column and the digits smooth at icon sizes.
"""

from __future__ import annotations

from PIL import Image, ImageChops, ImageDraw, ImageFont

from ..validation import require_non_empty_str, require_number_in_range, require_positive_int
from .theme import SURFACE_BASE, TRACK_OPACITY, TRANSPARENT, carries_light_text, hex_to_rgb, load_font

SUPERSAMPLE = 8

# The tank takes the whole cell, so the reading gets every pixel the taskbar
# gives it. Rounded rather than a capsule: a cell is square, so a capsule would
# be a circle and would give the reading less width than the cell actually has.
CORNER_RATIO = 0.26
DIGITS_HEIGHT_RATIO = 0.46
DIGITS_WIDTH_RATIO = 0.92

LIGHT_TEXT = (255, 255, 255, 255)

# What the number reads before the first reading has arrived. A dash has far
# less ink than a digit, so a digit is what its size is measured against.
NO_READING = "-"
NO_READING_REFERENCE = "0"


def _fit_font(draw: ImageDraw.ImageDraw, text: str, target_height: float, max_width: float) -> ImageFont.ImageFont:
	"""Return a bold font whose glyphs for a given text reach a target ink height.

	Font size is expressed in points rather than ink height, and the ratio
	between the two depends on which characters are drawn, so an initial guess is
	measured once and corrected. The result is then shrunk if needed so a wide
	string such as "100" still fits inside the tank.

	Args:
		draw: The drawing surface used for measurement. PIL.ImageDraw.ImageDraw.
		text: The characters that will be drawn. str, non-empty.
		target_height: Desired ink height of those characters in pixels. float,
			greater than 0.
		max_width: Largest ink width the text may occupy in pixels. float,
			greater than 0.

	Returns:
		PIL.ImageFont.ImageFont: The font to draw the text with.
	"""
	guess = max(1, int(round(target_height * 1.3)))
	font = load_font(guess)
	left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
	if bottom - top <= 0:
		return font
	size = max(1, int(round(guess * target_height / (bottom - top))))
	font = load_font(size)

	left, _, right, _ = draw.textbbox((0, 0), text, font=font)
	width = right - left
	if width > max_width and width > 0:
		font = load_font(max(1, int(round(size * max_width / width))))
	return font


def _text_layer(canvas_size: int, text: str, reference: str, color: tuple[int, int, int, int]) -> Image.Image:
	"""Render the reading centered on its own transparent layer.

	Args:
		canvas_size: Edge length of the square layer in pixels. int, greater than 0.
		text: The characters to draw. str, non-empty.
		reference: Characters to measure instead of the ones being drawn, for
			text whose own ink is not a fair guide to its size, such as a dash.
			str; empty means measure the text itself.
		color: RGBA text color. tuple of four ints.

	Returns:
		PIL.Image.Image: The layer, mode "RGBA", with the text at its center.
	"""
	layer = Image.new("RGBA", (canvas_size, canvas_size), TRANSPARENT)
	draw = ImageDraw.Draw(layer)
	font = _fit_font(
		draw,
		reference or text,
		canvas_size * DIGITS_HEIGHT_RATIO,
		canvas_size * DIGITS_WIDTH_RATIO,
	)
	left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
	center = canvas_size / 2.0
	draw.text((center - (right + left) / 2.0, center - (bottom + top) / 2.0), text, font=font, fill=color)
	return layer


def _below(layer: Image.Image, level: float) -> Image.Image:
	"""Return a copy of a layer with everything above a level erased.

	Args:
		layer: The layer to clip. PIL.Image.Image, mode "RGBA".
		level: Vertical position to clip at, in pixels. Everything above it is
			made transparent. float.

	Returns:
		PIL.Image.Image: The clipped layer, mode "RGBA".
	"""
	mask = Image.new("L", layer.size, 0)
	ImageDraw.Draw(mask).rectangle((0, level, layer.width, layer.height), fill=255)
	clipped = layer.copy()
	clipped.putalpha(ImageChops.multiply(clipped.split()[3], mask))
	return clipped


def _rgba(color: str) -> tuple[int, int, int, int]:
	"""Return a hexadecimal color as an opaque RGBA tuple.

	Args:
		color: The color as a "#rrggbb" string. str, non-empty.

	Returns:
		tuple[int, int, int, int]: The color with full alpha.
	"""
	require_non_empty_str(color, "color")
	return hex_to_rgb(color) + (255,)


def render_icon(percent: float | None, size: int, color: str) -> Image.Image:
	"""Render one notification area icon as a square RGBA image.

	Args:
		percent: Share of the displayed window already used, 0 to 100, or None
			when no reading has arrived yet, which draws a dash on an empty
			column. float or None.
		size: Width and height of the returned image in pixels. int, greater than 0.
		color: Color of the column, as a "#rrggbb" string. This is the color of
			the service, so two widgets can be told apart. str.

	Returns:
		PIL.Image.Image: The rendered icon, mode "RGBA", size by size pixels, on
		a transparent background.
	"""
	if percent is not None:
		require_number_in_range(percent, 0.0, 100.0, "percent")
	require_positive_int(size, "size")

	accent = _rgba(color)
	canvas_size = size * SUPERSAMPLE
	image = Image.new("RGBA", (canvas_size, canvas_size), TRANSPARENT)

	box = (0.0, 0.0, float(canvas_size - 1), float(canvas_size - 1))
	radius = canvas_size * CORNER_RATIO
	fraction = 0.0 if percent is None else percent / 100.0
	level = box[3] - (box[3] - box[1]) * fraction

	column = Image.new("RGBA", (canvas_size, canvas_size), TRANSPARENT)
	ImageDraw.Draw(column).rounded_rectangle(box, radius=radius, fill=accent[:3] + (int(round(255 * TRACK_OPACITY)),))
	image.alpha_composite(column)

	if fraction > 0.0:
		# The fill is the whole column clipped to below the level, so its bottom
		# keeps the rounded corners of the column and its top stays flat.
		filled = Image.new("RGBA", (canvas_size, canvas_size), TRANSPARENT)
		ImageDraw.Draw(filled).rounded_rectangle(box, radius=radius, fill=accent)
		image.alpha_composite(_below(filled, level))

	text = NO_READING if percent is None else f"{int(round(percent))}"
	reference = NO_READING_REFERENCE if percent is None else ""
	image.alpha_composite(_text_layer(canvas_size, text, reference, LIGHT_TEXT))
	if fraction > 0.0 and not carries_light_text(accent[:3]):
		image.alpha_composite(_below(_text_layer(canvas_size, text, reference, _rgba(SURFACE_BASE)), level))

	return image.resize((size, size), Image.LANCZOS)
