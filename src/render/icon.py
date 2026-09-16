"""Draw the notification area icons.

An icon is the reading as a number with a capsule bar under it, filled to the
same value and colored by the usage ramp. Giving the digits the full width of
the icon, rather than sharing it with the bar, is what makes them legible in a
taskbar cell.

Drawing happens on a supersampled canvas that is reduced at the end, which keeps
the rounded bar and the digits smooth at icon sizes.
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from ..validation import require_number_in_range, require_positive_int
from .theme import ICON_LABEL, TRACK_OPACITY, TRANSPARENT, load_font, usage_color

SUPERSAMPLE = 8

# The layout is expressed as fractions of the canvas edge, so one set of
# proportions serves every icon size the system asks for.
BAR_INSET = 0.03
BAR_CENTER = 0.84
BAR_THICKNESS = 0.18
DIGITS_HEIGHT = 0.54
DIGITS_CENTER = 0.34

# What the number reads before the first reading has arrived. A dash has far
# less ink than a digit, so a digit is what its size is measured against.
NO_READING = "-"
NO_READING_REFERENCE = "0"


def _fit_font(draw: ImageDraw.ImageDraw, text: str, target_height: float, max_width: float) -> ImageFont.ImageFont:
	"""Return a bold font whose glyphs for a given text reach a target ink height.

	Font size is expressed in points rather than ink height, and the ratio
	between the two depends on which characters are drawn, so an initial guess is
	measured once and corrected. The result is then shrunk if needed so a wide
	string such as "100%" still fits the space it has.

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


def _draw_centered_text(
	draw: ImageDraw.ImageDraw,
	text: str,
	center: tuple[float, float],
	target_height: float,
	max_width: float,
	reference: str = "",
) -> None:
	"""Paint text centered on a point, sized so its glyphs reach a target height.

	Args:
		draw: The drawing surface to paint on. PIL.ImageDraw.ImageDraw.
		text: The characters to paint. str, non-empty.
		center: Point the ink box is centered on as (x, y) in pixels. tuple of
			two floats.
		target_height: Desired ink height of the glyphs in pixels. float, greater
			than 0.
		max_width: Largest ink width the text may occupy in pixels. float,
			greater than 0.
		reference: Characters to measure instead of the ones being drawn, for
			text whose own ink is not a fair guide to its size, such as a dash.
			str; empty means measure the text itself.

	Returns:
		None.
	"""
	font = _fit_font(draw, reference or text, target_height, max_width)
	left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
	draw.text(
		(center[0] - (right + left) / 2.0, center[1] - (bottom + top) / 2.0),
		text,
		font=font,
		fill=ICON_LABEL,
	)


def _draw_capsule(
	draw: ImageDraw.ImageDraw,
	box: tuple[float, float, float, float],
	color: tuple[int, int, int, int],
) -> None:
	"""Paint a fully rounded horizontal bar inside a box.

	Args:
		draw: The drawing surface to paint on. PIL.ImageDraw.ImageDraw.
		box: The bar as (left, top, right, bottom) in pixels. tuple of four floats.
		color: RGBA fill color. tuple of four ints.

	Returns:
		None. Nothing is drawn for a box with no width.
	"""
	left, top, right, bottom = box
	if right <= left:
		return
	radius = (bottom - top) / 2.0
	# A fill shorter than the bar is round is drawn as the round end alone, so a
	# small reading still shows something rather than nothing.
	right = max(right, left + 2.0 * radius)
	draw.rounded_rectangle((left, top, right, bottom), radius=radius, fill=color)


def _draw_bar(draw: ImageDraw.ImageDraw, canvas_size: float, percent: float) -> None:
	"""Paint the track and the filled part of the bar.

	Args:
		draw: The drawing surface to paint on. PIL.ImageDraw.ImageDraw.
		canvas_size: Edge length of the drawing canvas in pixels. float.
		percent: Share of the window already used, 0 to 100. float.

	Returns:
		None.
	"""
	fill = usage_color(percent)
	track = fill[:3] + (int(round(255 * TRACK_OPACITY)),)

	left = canvas_size * BAR_INSET
	right = canvas_size - left
	thickness = canvas_size * BAR_THICKNESS
	top = canvas_size * BAR_CENTER - thickness / 2.0

	_draw_capsule(draw, (left, top, right, top + thickness), track)
	if percent > 0.0:
		_draw_capsule(draw, (left, top, left + (right - left) * percent / 100.0, top + thickness), fill)


def render_icon(percent: float | None, size: int) -> Image.Image:
	"""Render one notification area icon as a square RGBA image.

	Args:
		percent: Share of the displayed window already used, 0 to 100, or None
			when no reading has arrived yet, which draws a dash over an empty
			bar. float or None.
		size: Width and height of the returned image in pixels. int, greater than 0.

	Returns:
		PIL.Image.Image: The rendered icon, mode "RGBA", size by size pixels, on
		a transparent background.
	"""
	if percent is not None:
		require_number_in_range(percent, 0.0, 100.0, "percent")
	require_positive_int(size, "size")

	canvas_size = size * SUPERSAMPLE
	image = Image.new("RGBA", (canvas_size, canvas_size), TRANSPARENT)
	draw = ImageDraw.Draw(image)

	_draw_centered_text(
		draw,
		NO_READING if percent is None else f"{int(round(percent))}",
		(canvas_size / 2.0, canvas_size * DIGITS_CENTER),
		canvas_size * DIGITS_HEIGHT,
		canvas_size,
		reference=NO_READING_REFERENCE if percent is None else "",
	)
	_draw_bar(draw, canvas_size, 0.0 if percent is None else percent)
	return image.resize((size, size), Image.LANCZOS)
