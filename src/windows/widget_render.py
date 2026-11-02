"""Draw the desktop widgets, in the look of the Mac app's widgets.

A desktop widget is drawn whole by Pillow, background and all, and handed to
Windows as one picture with an alpha channel, so its rounded corners and its
type are smooth against whatever is behind it. Its card is either solid, the
surface of the palette it is given, which is the system's light or dark one or
one made for the color the user picked, or glass: the wallpaper behind it,
blurred and tinted light or dark, as the Mac app's clear widgets are. The small widget is the Mac
app's dial: the share inside an open arc in the service's color, the mark in
its gap. The medium widget is the Mac app's heading over rows: the mark and the
name, then each usage with its bar and its share.

Sizes are the Mac widget sizes, in points, scaled by the display.
"""

from __future__ import annotations

import math
from functools import lru_cache

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageStat

from src.common.render.logo import render_logo
from src.common.render.theme import Palette, contrast_ratio, load_font, mix_hex, readable_accent, track_hex, usage_hex
from src.common.ui.core import ProviderView
from src.common.usage.snapshot import SESSION_KEY, WEEKLY_KEY
from src.common.validation import require_member, require_number_in_range, require_type

SMALL = "small"
MEDIUM = "medium"

# The Mac widget sizes, in points.
SIZES = {SMALL: (170, 170), MEDIUM: (364, 170)}
# How round a widget's corners are, as on the Mac: 22 points, drawn as Apple's
# continuous corners, which ease into the straight edge rather than meeting it
# as a circle does. Such a corner starts about 1.53 radii from the corner, and
# is drawn here as a superellipse of that size, whose exponent puts its middle
# where Apple's is, a little further in than a circle's.
CORNER_RADIUS = 22
CONTINUOUS_EXTENT = 1.528
CONTINUOUS_EXPONENT = 3.0
CORNER_STEPS = 48
PADDING = 16

# The dial, as shares of the small widget's square, from the Mac app's
# DialGeometry: an arc of 270 degrees open at the bottom, with the mark in the gap.
DIAL_RADIUS = 0.40
DIAL_STROKE = 0.065
DIAL_START = 135
DIAL_SWEEP = 270
DIAL_NUMBER = 0.30
DIAL_MARK = 0.20
DIAL_MARK_CENTER = 0.82
TRACK_OPACITY = 0.22

# The heading and the rows of the medium widget, in points.
HEADING_MARK = 16
HEADING_FONT = 13
HEADING_GAP = 12
ROW_FONT = 13
ROW_HEIGHT = 20
ROW_GAP = 8
BAR_HEIGHT = 5
VALUE_WIDTH = 44
BAR_GAP = 10
LABEL_SHARE = 0.42
MAX_ROWS = 4

# Glass: how far the wallpaper is blurred, in points, how much white or black
# lies over it, and how much more colorful it is made.
GLASS_BLUR = 22
GLASS_TINT = {"light": ((255, 255, 255), 0.55), "dark": ((0, 0, 0), 0.45)}
# The contrast the text must have against the glass; the tint is laid on more
# heavily over a wallpaper that would not give it, up to GLASS_MAX_TINT.
TEXT_CONTRAST = 4.5
GLASS_MAX_TINT = 0.85
GLASS_TINT_STEP = 0.05
# How far toward the text the secondary and tertiary labels are mixed from a
# card's own color, so they read on any card.
SECONDARY_MIX = 0.8
TERTIARY_MIX = 0.66
GLASS_SATURATION = 1.4

# Drawn larger and reduced, so curves and type are smooth.
SUPERSAMPLE = 3

NOT_SIGNED_IN = "Sign in from FORL"
LOADING = "Loading"


def _rgba(color: str, alpha: float = 1.0) -> tuple[int, int, int, int]:
	"""Return a "#rrggbb" color with an opacity, as Pillow takes it.

	Args:
		color: The color. str, "#rrggbb".
		alpha: The opacity. float, 0 to 1.

	Returns:
		tuple: Red, green, blue and alpha, 0 to 255.
	"""
	require_number_in_range(alpha, 0.0, 1.0, "alpha")
	value = color.lstrip("#")
	return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), int(round(alpha * 255)))


def default_usages(size: str) -> list[str]:
	"""Return the usages a new widget of a size shows.

	Args:
		size: SMALL or MEDIUM. str.

	Returns:
		list of str: The current session, and the week where there is room.
	"""
	require_member(size, frozenset(SIZES), "size")
	return [SESSION_KEY] if size == SMALL else [SESSION_KEY, WEEKLY_KEY]


def _rows(view: ProviderView, usages: list[str], limit: int) -> list[tuple[str, float | None]]:
	"""Return the usages to draw, as label and share, in the order chosen.

	Args:
		view: The service. ProviderView.
		usages: Keys of the usages chosen. list of str.
		limit: The most rows there is room for. int.

	Returns:
		list: (label, share or None before a reading) for each chosen usage the
		reading has, or for the defaults when it has none of them.
	"""
	if view.snapshot is None:
		return []
	metrics = {metric.key: metric for metric in view.snapshot.metrics()}
	chosen = [metrics[key] for key in usages if key in metrics] or [metrics[key] for key in (SESSION_KEY, WEEKLY_KEY) if key in metrics]
	return [(metric.label, metric.percent) for metric in chosen[:limit]]


def glass(backdrop: Image.Image, tone: str, scale: float) -> Image.Image:
	"""Return the wallpaper behind a widget as frosted glass.

	Args:
		backdrop: The wallpaper behind the widget, at its size in pixels.
			PIL.Image.Image.
		tone: "light" or "dark", the tint laid over it. str.
		scale: Device pixels per point. float.

	Returns:
		PIL.Image.Image: The glass, mode "RGB", the backdrop's size.
	"""
	require_type(backdrop, Image.Image, "backdrop")
	require_member(tone, frozenset(GLASS_TINT), "tone")
	# Blurred small and enlarged: a wide blur costs much less on fewer pixels,
	# and enlarging what is already blurred loses nothing.
	small = backdrop.convert("RGB").resize((max(1, backdrop.width // 4), max(1, backdrop.height // 4)), Image.BILINEAR)
	blurred = small.filter(ImageFilter.GaussianBlur(GLASS_BLUR * scale / 4.0)).resize(backdrop.size, Image.BICUBIC)
	blurred = ImageEnhance.Color(blurred).enhance(GLASS_SATURATION)
	color, amount = GLASS_TINT[tone]
	text = "#000000" if tone == "light" else "#ffffff"
	tinted = Image.blend(blurred, Image.new("RGB", blurred.size, color), amount)
	while contrast_ratio(average_color(tinted), text) < TEXT_CONTRAST and amount < GLASS_MAX_TINT:
		amount = min(GLASS_MAX_TINT, amount + GLASS_TINT_STEP)
		tinted = Image.blend(blurred, Image.new("RGB", blurred.size, color), amount)
	return tinted


def card_palette(base: Palette, surface: str) -> Palette:
	"""Return a palette for text on a card of any color.

	Args:
		base: The palette whose primary text reads on the card, the light one
			for a light card and the dark one for a dark card. Palette.
		surface: The card's color, "#rrggbb". str.

	Returns:
		Palette: The base palette with the card as its surface and its lesser
		labels mixed from the card toward the text, so they keep their contrast.
	"""
	require_type(base, Palette, "base")
	return base._replace(
		surface=surface,
		label_secondary=mix_hex(surface, base.label_primary, SECONDARY_MIX),
		label_tertiary=mix_hex(surface, base.label_primary, TERTIARY_MIX),
	)


def average_color(image: Image.Image) -> str:
	"""Return the average color of a picture, which a glass widget's bars are mixed against.

	Args:
		image: The picture. PIL.Image.Image.

	Returns:
		str: The color as "#rrggbb".
	"""
	red, green, blue = (int(round(value)) for value in ImageStat.Stat(image.convert("RGB")).mean[:3])
	return f"#{red:02x}{green:02x}{blue:02x}"


@lru_cache(maxsize=8)
def _corner_mask(size: tuple[int, int], radius: float) -> Image.Image:
	"""Return the shape of a card: opaque inside its continuous rounded corners.

	Kept once made, because a glass widget is drawn again many times a second
	while it is dragged, at the same size every time.

	Args:
		size: The card's size, in pixels. tuple of two ints.
		radius: The corners' radius, in pixels. float.

	Returns:
		PIL.Image.Image: The mask, mode "L".
	"""
	big = (size[0] * SUPERSAMPLE, size[1] * SUPERSAMPLE)
	extent = min(radius * SUPERSAMPLE * CONTINUOUS_EXTENT, big[0] / 2.0, big[1] / 2.0)
	exponent = 2.0 / CONTINUOUS_EXPONENT
	# One quarter of a superellipse, from the top of a corner round to its side,
	# with (0, 0) at the corner's center.
	quarter = []
	for step in range(CORNER_STEPS + 1):
		angle = math.pi / 2.0 * step / CORNER_STEPS
		quarter.append((math.cos(angle) ** exponent, math.sin(angle) ** exponent))
	right, bottom = big[0] - 1, big[1] - 1
	outline = []
	for (cx, cy), (sx, sy) in (
		((right - extent, extent), (1, -1)),
		((extent, extent), (-1, -1)),
		((extent, bottom - extent), (-1, 1)),
		((right - extent, bottom - extent), (1, 1)),
	):
		points = [(cx + sx * x * extent, cy + sy * y * extent) for x, y in quarter]
		# Each corner is walked so the outline goes round the card in one direction.
		outline.extend(points if sx * sy < 0 else points[::-1])
	mask = Image.new("L", big, 0)
	ImageDraw.Draw(mask).polygon(outline, fill=255)
	return mask.resize(size, Image.LANCZOS)


def compose(content: Image.Image, palette: Palette, scale: float, surface: Image.Image | None = None) -> Image.Image:
	"""Return a widget: its content laid on its card, solid or of glass.

	Args:
		content: What the widget shows, from render_content. PIL.Image.Image.
		palette: The widget's colors, whose surface a solid card is. Palette.
		scale: Device pixels per point. float.
		surface: The glass behind the content, at the widget's size, or None
			for a solid card. PIL.Image.Image or None.

	Returns:
		PIL.Image.Image: The widget in mode "RGBA", transparent outside its
		rounded corners.
	"""
	require_type(content, Image.Image, "content")
	size = content.size
	card = Image.new("RGBA", size, _rgba(palette.surface)) if surface is None else surface.resize(size).convert("RGBA")
	card.putalpha(_corner_mask(size, CORNER_RADIUS * scale))
	card.alpha_composite(content)
	return card


def _arc_layer(size: int, fraction: float, width: float, color: tuple[int, int, int, int]) -> Image.Image:
	"""Return one stretch of the dial's arc, round at both ends, on a layer of its own.

	Drawn on its own layer and laid on once, so a translucent track is one even
	color, without the darker spots where a stroke and its round ends overlap.

	Args:
		size: The square's edge, in pixels. int.
		fraction: How much of the sweep, 0 to 1. float.
		width: The stroke, in pixels. float.
		color: The stretch's color, opaque. tuple.

	Returns:
		PIL.Image.Image: The stretch, white where drawn, to be colored by the caller.
	"""
	layer = Image.new("L", (size, size), 0)
	draw = ImageDraw.Draw(layer)
	radius = size * DIAL_RADIUS
	center = size / 2.0
	end = DIAL_START + DIAL_SWEEP * fraction
	box = (center - radius, center - radius, center + radius, center + radius)
	draw.arc(box, DIAL_START, end, fill=255, width=int(round(width)))
	for degrees in (DIAL_START, end):
		# The arc is drawn inward from its box, so its middle line is half a
		# stroke inside the radius.
		middle = radius - width / 2.0
		x = center + middle * math.cos(math.radians(degrees))
		y = center + middle * math.sin(math.radians(degrees))
		draw.ellipse((x - width / 2.0, y - width / 2.0, x + width / 2.0, y + width / 2.0), fill=255)
	solid = Image.new("RGBA", (size, size), color[:3] + (255,))
	alpha = layer.point(lambda value: value * color[3] // 255)
	solid.putalpha(alpha)
	return solid


def _small(image: Image.Image, view: ProviderView, usages: list[str], palette: Palette, scale: float) -> None:
	"""Draw the small widget: one usage, as the Mac app's dial.

	Args:
		image: The supersampled widget, background already filled. PIL.Image.Image.
		view: The service. ProviderView.
		usages: Keys of the usages chosen; the first is drawn. list of str.
		palette: The colors of the system's mode. Palette.
		scale: Pixels per point, supersampling included. float.

	Returns:
		None.
	"""
	edge = image.width
	accent = readable_accent(view.provider.accent, palette)
	rows = _rows(view, usages, 1)
	percent = rows[0][1] if rows else None
	stroke = edge * DIAL_STROKE
	image.alpha_composite(_arc_layer(edge, 1.0, stroke, _rgba(accent, TRACK_OPACITY)))
	if percent is not None and percent > 0:
		image.alpha_composite(_arc_layer(edge, min(100.0, percent) / 100.0, stroke, _rgba(accent)))

	draw = ImageDraw.Draw(image)
	font = load_font(int(edge * DIAL_NUMBER), "bold")
	text = "-" if percent is None else str(int(round(percent)))
	draw.text((edge / 2.0, edge / 2.0), text, font=font, fill=_rgba(palette.label_primary), anchor="mm")
	mark_size = int(edge * DIAL_MARK)
	mark = render_logo(view.provider.logo_file, mark_size, accent)
	image.alpha_composite(mark, (int((edge - mark_size) / 2), int(edge * DIAL_MARK_CENTER - mark_size / 2)))


def _medium(image: Image.Image, view: ProviderView, usages: list[str], palette: Palette, scale: float) -> None:
	"""Draw the medium widget: the service's heading over a row per usage.

	Rows start under the heading and end at the bottom padding at the latest, so
	the space around the content is the same on every side once it is full.

	Args:
		image: The supersampled widget, background already filled. PIL.Image.Image.
		view: The service. ProviderView.
		usages: Keys of the usages chosen, in order. list of str.
		palette: The colors of the system's mode. Palette.
		scale: Pixels per point, supersampling included. float.

	Returns:
		None.
	"""
	draw = ImageDraw.Draw(image)
	pad = PADDING * scale
	right = image.width - pad
	accent = readable_accent(view.provider.accent, palette)

	mark_size = int(HEADING_MARK * scale)
	image.alpha_composite(render_logo(view.provider.logo_file, mark_size, accent), (int(pad), int(pad)))
	heading_font = load_font(int(HEADING_FONT * scale), "bold")
	draw.text((pad + mark_size + 8 * scale, pad + mark_size / 2.0), view.provider.label, font=heading_font, fill=_rgba(palette.label_primary), anchor="lm")
	if view.snapshot is not None and view.snapshot.plan:
		label_end = pad + mark_size + 8 * scale + draw.textlength(view.provider.label, font=heading_font)
		plan_font = load_font(int(11 * scale), "bold")
		draw.text((label_end + 8 * scale, pad + mark_size / 2.0), view.snapshot.plan, font=plan_font, fill=_rgba(palette.label_tertiary), anchor="lm")

	y = pad + mark_size + HEADING_GAP * scale
	row_font = load_font(int(ROW_FONT * scale), "normal")
	value_font = load_font(int(ROW_FONT * scale), "bold")
	rows = _rows(view, usages, MAX_ROWS)
	if not rows:
		message = LOADING if view.signed_in else NOT_SIGNED_IN
		draw.text((pad, y + ROW_HEIGHT * scale / 2.0), message, font=row_font, fill=_rgba(palette.label_secondary), anchor="lm")
		return

	inner = right - pad
	bar_left = pad + inner * LABEL_SHARE
	bar_right = right - VALUE_WIDTH * scale - BAR_GAP * scale
	bar_height = BAR_HEIGHT * scale
	for label, percent in rows:
		middle = y + ROW_HEIGHT * scale / 2.0
		name = label
		while name and draw.textlength(name, font=row_font) > bar_left - pad - BAR_GAP * scale:
			name = name[:-1]
		if name != label:
			name = name[:-1].rstrip() + "..."
		draw.text((pad, middle), name, font=row_font, fill=_rgba(palette.label_primary), anchor="lm")
		share = percent if percent is not None else 0.0
		top = middle - bar_height / 2.0
		draw.rounded_rectangle((bar_left, top, bar_right, top + bar_height), radius=bar_height / 2.0, fill=_rgba(track_hex(share, palette.surface)))
		filled = (bar_right - bar_left) * min(100.0, share) / 100.0
		if filled > 0:
			draw.rounded_rectangle((bar_left, top, bar_left + max(bar_height, filled), top + bar_height), radius=bar_height / 2.0, fill=_rgba(usage_hex(share)))
		value = "-" if percent is None else f"{int(round(percent))}%"
		draw.text((right, middle), value, font=value_font, fill=_rgba(palette.label_primary), anchor="rm")
		y += (ROW_HEIGHT + ROW_GAP) * scale


def render_content(size: str, view: ProviderView, usages: list[str], palette: Palette, scale: float) -> Image.Image:
	"""Return what a widget shows, on nothing, at its size in pixels.

	Drawn apart from the card so a glass widget being dragged can be laid on new
	glass at every step without drawing its type and its dial again.

	Args:
		size: SMALL or MEDIUM. str.
		view: The service it shows. ProviderView.
		usages: Keys of the usages chosen, in order. list of str.
		palette: The widget's colors. Palette.
		scale: Device pixels per point. float, greater than 0.

	Returns:
		PIL.Image.Image: The content in mode "RGBA", transparent around it.
	"""
	require_member(size, frozenset(SIZES), "size")
	require_type(view, ProviderView, "view")
	require_type(usages, list, "usages")
	require_number_in_range(scale, 0.5, 8.0, "scale")
	width, height = SIZES[size]
	final = (int(round(width * scale)), int(round(height * scale)))
	image = Image.new("RGBA", (final[0] * SUPERSAMPLE, final[1] * SUPERSAMPLE), (0, 0, 0, 0))
	if size == SMALL:
		_small(image, view, usages, palette, scale * SUPERSAMPLE)
	else:
		_medium(image, view, usages, palette, scale * SUPERSAMPLE)
	return image.resize(final, Image.LANCZOS)


def render_widget(
	size: str,
	view: ProviderView,
	usages: list[str],
	palette: Palette,
	scale: float,
	surface: Image.Image | None = None,
) -> Image.Image:
	"""Return a desktop widget, drawn whole, ready to hand to Windows.

	Args:
		size: SMALL or MEDIUM. str.
		view: The service it shows. ProviderView.
		usages: Keys of the usages chosen, in order. list of str.
		palette: The widget's colors: the system's light or dark ones, or ones
			made for its custom background or its glass. Palette.
		scale: Device pixels per point. float, greater than 0.
		surface: Glass to draw the widget on, from glass(), at the widget's
			size in pixels, or None for a solid card. PIL.Image.Image or None.

	Returns:
		PIL.Image.Image: The widget in mode "RGBA", transparent outside its
		rounded corners.
	"""
	return compose(render_content(size, view, usages, palette, scale), palette, scale, surface)
