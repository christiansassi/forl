"""Palette, type ramp and metrics shared by the tray icons and the panel.

Two color ideas live here. A brand accent marks the parts of the interface that
belong to the product, the mark, the refresh control and the spinner; it comes
from the provider, so the panel is orange for Claude and follows the text color
for ChatGPT, whose mark is monochrome. The usage ramp is a separate scale that
runs from green to red with the percentage, so a bar says how close to its limit
it is by color alone, without anyone having to read the number.

The surfaces and the text follow Windows. There is one palette for the light
app mode and one for the dark, both taken from the colors Windows 11 draws its
own flyouts in, and the popups ask which one is in force each time they open,
so they match the rest of the desktop rather than keeping a look of their own.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from ..validation import require_member, require_non_empty_str, require_number_in_range, require_positive_int, require_type

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

# Opacity of the switch track when it is off, laid over the surface.
SWITCH_OFF_OPACITY = 0.22

# Contrast below which white stops reading against a color and the dark
# surface is used instead. Measured as the WCAG ratio, whose floor for large
# bold text is 3 to 1; a mark larger than text carries a little less.
MIN_LIGHT_CONTRAST = 2.5

# The two inks laid over a colored fill, such as the knob of a switch or the
# reading on a tray icon: white, and a near black for a fill too pale to carry
# white. They do not change with the app mode, because the fill under them
# does not either.
SURFACE_BASE = "#1c1c1e"
LABEL_PRIMARY = "#ffffff"

# Contrast below which an accent no longer reads as a mark on a surface, and the
# text color of that surface stands in for it. The OpenAI mark is white, which
# vanishes on a light surface, so this is what turns it dark there.
MIN_ACCENT_CONTRAST = 2.0


class Palette(NamedTuple):
	"""The surface and text colors of one app mode.

	Attributes:
		dark: Whether this is the dark mode, which the window manager is told so
			the corners and the border are drawn to match. bool.
		surface: Background of a popup. str, "#rrggbb".
		label_primary: Text that is read first, such as a name or a title. str,
			"#rrggbb".
		label_secondary: Text that describes, such as a percentage or a reset
			time. str, "#rrggbb".
		label_tertiary: Text that only annotates, such as the plan beside the
			product name. str, "#rrggbb".
	"""

	dark: bool
	surface: str
	label_primary: str
	label_secondary: str
	label_tertiary: str


# The Windows 11 flyout surface and the three text fill colors, flattened onto
# that surface: Tk draws opaque colors only, so each text color, which Windows
# defines as the foreground at an opacity, is given as the color it comes out.
DARK_PALETTE = Palette(
	dark=True,
	surface="#2c2c2c",
	label_primary="#ffffff",
	label_secondary="#cecece",
	label_tertiary="#9c9c9c",
)
LIGHT_PALETTE = Palette(
	dark=False,
	surface="#f9f9f9",
	label_primary="#1a1a1a",
	label_secondary="#5f5f5f",
	label_tertiary="#8a8a8a",
)

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


def hex_to_rgb(color: str) -> tuple[int, int, int]:
	"""Return a hexadecimal color as its three components.

	Args:
		color: The color as a "#rrggbb" string, with or without the hash. str,
			non-empty.

	Returns:
		tuple[int, int, int]: The red, green and blue components, each 0 to 255.
	"""
	require_non_empty_str(color, "color")
	value = color.lstrip("#")
	return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def relative_luminance(color: tuple[int, int, int]) -> float:
	"""Return the relative luminance of a color, as the sRGB definition gives it.

	Args:
		color: The red, green and blue components, each 0 to 255. tuple of three
			ints.

	Returns:
		float: The luminance, 0 for black and 1 for white.
	"""
	channels = []
	for value in color[:3]:
		share = value / 255.0
		channels.append(share / 12.92 if share <= 0.04045 else ((share + 0.055) / 1.055) ** 2.4)
	return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def carries_light_text(color: tuple[int, int, int]) -> bool:
	"""Return whether white reads against a color.

	Used wherever something white is laid over a colored fill, which is the
	reading on a tray icon and the knob of a switch: one accent is orange and
	carries white, the other is white and does not.

	Args:
		color: The fill color as red, green and blue, each 0 to 255. tuple of
			three ints.

	Returns:
		bool: True when white has enough contrast against it.
	"""
	return 1.05 / (relative_luminance(color) + 0.05) >= MIN_LIGHT_CONTRAST


def contrast_ratio(first: str, second: str) -> float:
	"""Return the WCAG contrast ratio between two colors.

	Args:
		first: One color as a "#rrggbb" string. str, non-empty.
		second: The other color as a "#rrggbb" string. str, non-empty.

	Returns:
		float: The ratio, 1 for two identical colors and 21 for black on white.
	"""
	one = relative_luminance(hex_to_rgb(first))
	two = relative_luminance(hex_to_rgb(second))
	return (max(one, two) + 0.05) / (min(one, two) + 0.05)


def readable_accent(accent: str, palette: Palette) -> str:
	"""Return the color a brand accent is drawn in on a palette's surface.

	Args:
		accent: The provider's accent as a "#rrggbb" string. str, non-empty.
		palette: The palette in force. Palette.

	Returns:
		str: The accent itself when it reads against the surface, otherwise the
		primary text color of the palette.
	"""
	require_non_empty_str(accent, "accent")
	require_type(palette, Palette, "palette")
	if contrast_ratio(accent, palette.surface) < MIN_ACCENT_CONTRAST:
		return palette.label_primary
	return accent


def on_accent(accent: str) -> str:
	"""Return the color to lay over a brand accent so it stays visible.

	Args:
		accent: The accent as a "#rrggbb" string. str, non-empty.

	Returns:
		str: White when the accent is dark enough to carry it, otherwise the
		panel surface.
	"""
	return LABEL_PRIMARY if carries_light_text(hex_to_rgb(accent)) else SURFACE_BASE


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
	lower = hex_to_rgb(background)
	upper = hex_to_rgb(foreground)
	blended = tuple(int(round(low + (high - low) * amount)) for low, high in zip(lower, upper))
	return "#{:02x}{:02x}{:02x}".format(*blended)


def track_hex(percent: float, surface: str) -> str:
	"""Return the track color for a bar, which is the bar color dimmed.

	Args:
		percent: Share of the window already used, 0 to 100. float.
		surface: The color the bar is drawn on, as a "#rrggbb" string. str,
			non-empty.

	Returns:
		str: The color as a "#rrggbb" string.
	"""
	require_non_empty_str(surface, "surface")
	return mix_hex(surface, usage_hex(percent), TRACK_OPACITY)


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
