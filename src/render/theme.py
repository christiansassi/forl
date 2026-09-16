"""Palette, type ramp and metrics shared by the tray icons and the panel.

Two color ideas live here. A brand accent marks the parts of the interface that
belong to the product, the mark, the refresh control and the spinner; it comes
from the provider, so the panel is orange for Claude and green for ChatGPT. The
usage ramp is a separate scale that runs from green to red with the percentage,
so a bar says how close to its limit it is by color alone, without anyone having
to read the number.

The rest follows Apple's dark system palette and type scale: a near black
background, label colors expressed as white at decreasing prominence, and a
small set of named text styles built from size and weight together.
"""

from __future__ import annotations

from pathlib import Path

from ..validation import require_member, require_number_in_range, require_positive_int

# Stops of the usage ramp as (percentage, (red, green, blue)). A value between
# two stops is mixed from them, so the bar shifts continuously rather than
# jumping at a threshold.
USAGE_RAMP = (
	(0.0, (48, 209, 88)),
	(50.0, (227, 193, 59)),
	(75.0, (232, 145, 45)),
	(100.0, (255, 69, 58)),
)

# Opacity of a bar track, which is the bar color laid over the background.
TRACK_OPACITY = 0.22

ICON_LABEL = (255, 255, 255, 255)
TRANSPARENT = (0, 0, 0, 0)

SURFACE_BASE = "#1c1c1e"

# Label colors, brightest first, matching label, secondary and tertiary.
LABEL_PRIMARY = "#ffffff"
LABEL_SECONDARY = "#a1a1a6"
LABEL_TERTIARY = "#6e6e73"

UI_FONT_FAMILY = "Segoe UI"

# Size and weight together, in the order of Apple's text styles. Sizes are in
# points, so Windows scales them with the display and the user text size.
TEXT_STYLES = {
	"title": (12, "bold"),
	"section": (10, "bold"),
	"row": (10, "normal"),
	"row_value": (10, "normal"),
	"caption": (8, "normal"),
	"caption_strong": (8, "bold"),
}

FONT_CANDIDATES = {
	"bold": (
		"C:/Windows/Fonts/segoeuib.ttf",
		"C:/Windows/Fonts/seguisb.ttf",
		"C:/Windows/Fonts/arialbd.ttf",
		"C:/Windows/Fonts/DejaVuSans-Bold.ttf",
	),
	"normal": (
		"C:/Windows/Fonts/segoeui.ttf",
		"C:/Windows/Fonts/arial.ttf",
		"C:/Windows/Fonts/DejaVuSans.ttf",
	),
}


def usage_rgb(percent: float) -> tuple[int, int, int]:
	"""Return the ramp color for a usage percentage.

	Args:
		percent: Share of a window already used, 0 to 100. float.

	Returns:
		tuple[int, int, int]: The red, green and blue components, each 0 to 255.
	"""
	require_number_in_range(percent, 0.0, 100.0, "percent")
	previous_stop, previous_color = USAGE_RAMP[0]
	for stop, color in USAGE_RAMP:
		if percent <= stop:
			span = stop - previous_stop
			ratio = 0.0 if span <= 0.0 else (percent - previous_stop) / span
			return tuple(int(round(low + (high - low) * ratio)) for low, high in zip(previous_color, color))
		previous_stop, previous_color = stop, color
	return USAGE_RAMP[-1][1]


def usage_color(percent: float) -> tuple[int, int, int, int]:
	"""Return the ramp color for a usage percentage as an opaque RGBA tuple.

	Args:
		percent: Share of a window already used, 0 to 100. float.

	Returns:
		tuple[int, int, int, int]: The RGBA color to fill an icon bar with.
	"""
	return usage_rgb(percent) + (255,)


def usage_hex(percent: float) -> str:
	"""Return the ramp color for a usage percentage as a hexadecimal string.

	Tkinter accepts hexadecimal strings rather than RGBA tuples, so the ramp is
	exposed in both forms.

	Args:
		percent: Share of a window already used, 0 to 100. float.

	Returns:
		str: The color as a "#rrggbb" string.
	"""
	return "#{:02x}{:02x}{:02x}".format(*usage_rgb(percent))


def text_style(name: str) -> tuple[str, int, str]:
	"""Return a named text style as a Tk font specification.

	Args:
		name: A key of TEXT_STYLES, such as "title" or "caption". str.

	Returns:
		tuple[str, int, str]: The family, size in points and weight, ready to
		pass as a Tk font option.
	"""
	require_member(name, frozenset(TEXT_STYLES), "name")
	size, weight = TEXT_STYLES[name]
	return (UI_FONT_FAMILY, size, weight)


def mix_hex(background: str, foreground: str, amount: float) -> str:
	"""Return the color that results from laying one color over another.

	Tkinter has no alpha channel, so translucent tracks and pressed states are
	flattened against the surface they sit on.

	Args:
		background: The lower color as a "#rrggbb" string. str.
		foreground: The upper color as a "#rrggbb" string. str.
		amount: Opacity of the upper color, 0 to 1. float.

	Returns:
		str: The blended color as a "#rrggbb" string.
	"""
	require_number_in_range(amount, 0.0, 1.0, "amount")
	lower = tuple(int(background.lstrip("#")[index : index + 2], 16) for index in (0, 2, 4))
	upper = tuple(int(foreground.lstrip("#")[index : index + 2], 16) for index in (0, 2, 4))
	blended = tuple(int(round(low + (high - low) * amount)) for low, high in zip(lower, upper))
	return "#{:02x}{:02x}{:02x}".format(*blended)


def track_hex(percent: float) -> str:
	"""Return the track color for a bar, which is the bar color dimmed.

	Args:
		percent: Share of the window already used, 0 to 100. float.

	Returns:
		str: The color as a "#rrggbb" string.
	"""
	return mix_hex(SURFACE_BASE, usage_hex(percent), TRACK_OPACITY)


def load_font(size: int, weight: str = "bold"):
	"""Return a TrueType font of the platform family at the requested size.

	Pillow needs a face on disk where Tk takes a family name, so the same type
	the panel sets in Tk is loaded here by file.

	Falls back to the Pillow bitmap font when no candidate face is installed, so
	rendering never fails on a machine with an unusual font set.

	Args:
		size: Font size in pixels. int, greater than 0.
		weight: Either "normal" or "bold". str.

	Returns:
		PIL.ImageFont.ImageFont: A font object usable with ImageDraw.text.
	"""
	require_positive_int(size, "size")
	require_member(weight, frozenset(FONT_CANDIDATES), "weight")
	from PIL import ImageFont

	for candidate in FONT_CANDIDATES[weight]:
		if Path(candidate).exists():
			try:
				return ImageFont.truetype(candidate, size)
			except OSError:
				continue
	return ImageFont.load_default()
