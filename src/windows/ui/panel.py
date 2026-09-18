"""The panel that opens when a notification area icon is clicked.

The layout follows Claude's own usage view, and serves ChatGPT just as well:
each row puts the name and what it covers on the left, a thin bar across the
middle, and the percentage on the right, with any split by product in its own
titled section. Everything is drawn on a single canvas rather than assembled
from Tk widgets, which is what allows that three column alignment and lets the
bars animate: their fill is driven by springs, so a refresh moves each bar from
where it is rather than snapping it to the new value.

The panel itself appears and disappears at once, with no transition. The bars
animate, and only when the Windows animation preference allows it, and a line in
the footer counts down the seconds to the next reading.

The same window carries a second view. The gear at the top right of the reading
leads to the settings, the chevron at the top left of the settings leads back,
and the two are drawn on the same canvas rather than in two windows, so the
panel keeps its position and its chrome across the change. The window takes
whichever of the two views is taller, which is the reading once one has been
taken, so opening the settings does not resize it.

Nothing here is a Tk widget, so anything that can be clicked registers the area
that reaches it and the canvas looks the pointer up there. Each of those also
registers how to light itself, because a gear is an image and a word is canvas
text and the two are lit differently. Whatever the pointer is over turns the
color of the service, rather than lighting a plate behind it, so the panel keeps
one flat background throughout.
"""

from __future__ import annotations

import time
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime, timezone
from typing import Callable

from PIL import Image, ImageTk

from ..providers import Provider
from ..render.glyphs import render_back, render_gear
from ..render.logo import render_logo
from ..render.theme import (
	LABEL_PRIMARY,
	LABEL_SECONDARY,
	LABEL_TERTIARY,
	SURFACE_BASE,
	SWITCH_OFF_OPACITY,
	mix_hex,
	text_style,
	track_hex,
	usage_hex,
)
from ..usage.snapshot import PRODUCT_KEY_PREFIX, UsageSnapshot
from ..validation import require_member, require_non_empty_str, require_type
from .animation import Spring, Ticker
from .capsule_bar import CapsuleBar
from .switch import Switch
from ..system import animations_enabled, apply_panel_chrome, work_area
from .formatting import format_percent, format_subtitle

PANEL_WIDTH = 430
PANEL_PAD = 20
SCREEN_MARGIN = 10

LABEL_COLUMN_WIDTH = 176
BAR_COLUMN_LEFT = 206
VALUE_COLUMN_WIDTH = 46
BAR_HEIGHT = 5

LOGO_SIZE = 17
LOGO_TITLE_GAP = 9
PLAN_GAP = 10
HEADER_GAP = 14

# The gear, and how far beyond its own edges a click still reaches it. A mark
# this small is hard to hit exactly, so the area that answers is larger than the
# mark that is drawn. The reach is the same on every side of every mark.
CONTROL_SIZE = 16
CONTROL_HIT_PAD = 7

# Height of the chevron as a share of the gear, which is the reference for both.
# A chevron drawn as tall as the gear reads larger than it: two thin strokes
# crossing a box carry far less ink than a disc that fills the same box.
BACK_SIZE_RATIO = 0.8

# Height of a capital as a share of the type size. Anything set beside a line
# of text, a mark or a control, is centered on the capitals rather than on the
# line box Tk reports, which reserves room under the baseline for descenders the
# line may not have and would leave its neighbour sitting low.
CAP_HEIGHT_RATIO = 0.70

USAGE_VIEW = "usage"
SETTINGS_VIEW = "settings"
PANEL_VIEWS = frozenset((USAGE_VIEW, SETTINGS_VIEW))

GEAR_KEY = "gear"
BACK_KEY = "back"
STARTUP_KEY = "startup"
ACCOUNT_KEY = "account"
SIGN_IN_LINK_KEY = "sign_in_link"

SETTINGS_TITLE = "Settings"
STARTUP_LABEL = "Start at login"
ACCOUNT_LABEL = "Account"
SIGN_OUT_LABEL = "Sign out"
SIGN_IN_LABEL = "Sign in"
NOT_SIGNED_IN_LABEL = "Not signed in"

SWITCH_WIDTH = 40
SWITCH_HEIGHT = 24

# A setting is the same shape as a usage row, a name on the left and one control
# on the right, and is set on the same rhythm so the two views read alike.
SETTINGS_ROW_MIN_HEIGHT = 34
SETTINGS_ROW_GAP = 14

# Space between a setting's name and the line set under it, which is the same
# gap a usage row leaves between a limit and what it covers.
SETTINGS_CAPTION_GAP = 2

# How far past a word a click still reaches it. A word is a smaller target than
# a mark, but it is also wider, so it needs less help.
ACTION_HIT_PAD = 5

# What a name too long for its room ends with. Three periods rather than the
# single character, so the file stays in the alphabet the rest of it is in.
ELLIPSIS = "..."

# The address a sign-in is waiting at, offered while one is under way. It is
# the one thing drawn in the provider's own color, because it is the one thing
# on the panel that is neither a reading nor a control but somewhere to go.
LINK_GAP = 7
LINK_CAPTION_GAP = 5
LINK_COPIED_TEXT = "Copied. Paste it in a browser if none opened."

SUBTITLE_OFFSET = 17
LIMIT_ROW_MIN_HEIGHT = 34
LIMIT_ROW_GAP = 14
PRODUCT_ROW_MIN_HEIGHT = 22
PRODUCT_ROW_GAP = 10
SECTION_TITLE_GAP = 26

SPINNER_SIZE = 13
SPINNER_EXTENT = 110
SPINNER_STROKE = 2.0
SPINNER_DEGREES_PER_SECOND = 320

# Tk measures type in points and Pillow in pixels.
PIXELS_PER_POINT = 96.0 / 72.0

BAR_RESPONSE = 0.45

PRODUCT_SECTION_TITLE = "This week's usage by product"
STATUS_INTERVAL_MS = 1000

# Clicking a tray icon takes focus away from the panel, which dismisses it
# before the click is delivered. A dismissal this recent is treated as part of
# that click, so the click closes the panel instead of closing and reopening it.
CLICK_DISMISS_SECONDS = 0.4


class Panel:
	"""A hidden-by-default flyout showing every usage the account reports."""

	def __init__(
		self,
		master: tk.Tk,
		provider: Provider,
		status_text: Callable[[], str],
		on_startup_change: Callable[[bool], None],
		on_sign_in: Callable[[], None],
		on_sign_out: Callable[[], None],
		on_open_sign_in: Callable[[], None],
	) -> None:
		"""Create the panel as a hidden child of the application root window.

		Args:
			master: The application root window. tkinter.Tk.
			provider: The service being reported on, which names and colors the
				panel. Provider.
			status_text: Returns the line under the reading, which is either the
				sign-in instruction or the countdown to the next reading. Asked
				again every second while the panel is open, because the countdown
				changes without a new reading arriving. Callable taking no
				arguments and returning str.
			on_startup_change: Called with the new value whenever the user works
				the start on startup switch. The panel shows the switch and does
				not store or act on it. Callable taking one bool and returning
				None.
			on_sign_in: Called when the user asks to sign in. Runs the browser
				sign-in, which takes as long as the user does, so it belongs
				somewhere other than the thread this panel is drawn on. Callable
				taking no arguments and returning None.
			on_sign_out: Called when the user asks to sign out, which is also how
				they move the widget to another subscription. Callable taking no
				arguments and returning None.
			on_open_sign_in: Called when the user clicks the sign-in address. The
				panel puts it on the clipboard itself and leaves opening it to
				the owner. Callable taking no arguments and returning None.

		Returns:
			None.
		"""
		require_type(master, tk.Tk, "master")
		require_type(provider, Provider, "provider")
		for name, callback in (
			("status_text", status_text),
			("on_startup_change", on_startup_change),
			("on_sign_in", on_sign_in),
			("on_sign_out", on_sign_out),
			("on_open_sign_in", on_open_sign_in),
		):
			if not callable(callback):
				raise TypeError(f"{name} must be callable")

		self._provider = provider
		self._status_text = status_text
		self._on_startup_change = on_startup_change
		self._on_sign_in = on_sign_in
		self._on_sign_out = on_sign_out
		self._on_open_sign_in = on_open_sign_in
		self._visible = False
		self._view = USAGE_VIEW
		self._start_on_startup = True
		self._hits: list[tuple[tuple[float, float, float, float], str]] = []
		self._lit: dict[str, Callable[[bool], None]] = {}
		self._control_photos: list[ImageTk.PhotoImage] = []
		self._hovered = ""
		self._switch: Switch | None = None
		self._account = ""
		self._signed_in = False
		self._sign_in_link = ""
		self._link_caption_item = 0
		self._snapshot: UsageSnapshot | None = None
		self._sign_in_message = ""
		self._refreshing = False
		self._bars: list[tuple[CapsuleBar, Spring]] = []
		self._springs: dict[str, Spring] = {}
		self._content_height = 0
		self._scroll_offset = 0.0
		self._status_item = 0
		self._spinner_item = 0
		self._status_job: str | None = None
		self._logo_photo: ImageTk.PhotoImage | None = None
		self._fonts: dict[tuple[str, int, str], tkfont.Font] = {}
		self._ascents: dict[tuple[str, int, str], int] = {}
		self._spinner_angle = 90.0
		self._scale = 1.0
		self._usage_height = 0
		self._hidden_at = 0.0

		self._window = tk.Toplevel(master)
		self._window.withdraw()
		self._window.title(f"{provider.label} usage")
		self._window.overrideredirect(True)
		self._window.attributes("-topmost", True)
		self._window.resizable(False, False)
		self._window.configure(background=SURFACE_BASE)
		self._window.bind("<Escape>", lambda _event: self.hide())
		self._window.bind("<FocusOut>", lambda _event: self.hide())
		self._window.bind("<MouseWheel>", self._on_mouse_wheel)

		self._canvas = tk.Canvas(
			self._window,
			background=SURFACE_BASE,
			highlightthickness=0,
			borderwidth=0,
		)
		self._canvas.pack(fill="both", expand=True)
		self._canvas.bind("<MouseWheel>", self._on_mouse_wheel)
		self._canvas.bind("<Button-1>", self._on_click)
		self._canvas.bind("<Motion>", self._on_motion)
		self._canvas.bind("<Leave>", self._on_leave)

		self._ticker = Ticker(self._window, self._on_frame)

	def _unit(self, value: float) -> float:
		"""Return a layout distance converted from layout units to device pixels.

		The layout is written at the scale of a 96 dot per inch display, so every
		distance passes through here and comes back matching the display the
		panel is on.

		Args:
			value: The distance in layout units. float.

		Returns:
			float: The distance in device pixels.
		"""
		return value * self._scale

	def _text(
		self,
		position: tuple[float, float],
		text: str,
		style: str,
		color: str,
		anchor: str = "nw",
		width: float = 0.0,
		tags: str = "content",
	) -> int:
		"""Draw one run of text and return its canvas item id.

		Args:
			position: Anchor point as (x, y) in device pixels. tuple of two floats.
			text: The characters to draw. str.
			style: A key of the theme text styles, such as "row". str.
			color: Text color as a "#rrggbb" string. str.
			anchor: Tk anchor naming which point of the text sits at the position.
				str.
			width: Wrapping width in device pixels, or 0 for no wrapping. float.
			tags: Tags to attach to the item. str, non-empty.

		Returns:
			int: The canvas item id of the text.
		"""
		return self._canvas.create_text(
			position[0],
			position[1],
			text=text,
			font=text_style(style),
			fill=color,
			anchor=anchor,
			width=width,
			tags=tags,
		)

	def _bar(self, box: tuple[float, float, float, float], key: str, fraction: float, percent: float) -> None:
		"""Draw one capsule bar and bind it to the spring that fills it.

		A bar keeps its spring across rebuilds, so a refresh animates from the
		value already on screen instead of starting again from empty.

		Args:
			box: The bar as (left, top, right, bottom) in device pixels. tuple of
				four floats.
			key: Stable identifier of the value this bar shows. str, non-empty.
			fraction: Share of the bar that should end up filled, 0 to 1. float.
			percent: The reading the bar shows, which picks its color off the
				usage ramp. float, 0 to 100.

		Returns:
			None.
		"""
		require_non_empty_str(key, "key")
		spring = self._springs.get(key)
		if spring is None:
			spring = Spring(0.0, response=BAR_RESPONSE, damping=1.0)
			self._springs[key] = spring
		spring.set_target(fraction)
		bar = CapsuleBar(self._canvas, box, track_hex(percent), usage_hex(percent), "content")
		bar.set_fraction(min(1.0, max(0.0, spring.value)))
		self._bars.append((bar, spring))

	def _draw_row(
		self,
		key: str,
		label: str,
		subtitle: str,
		percent: float,
		y: float,
		min_height: float,
	) -> float:
		"""Draw one usage row and return the vertical cursor at its bottom.

		The name and its subtitle set the height of the row, and the bar and the
		percentage are centered against that block, so a row whose subtitle wraps
		onto a second line stays aligned with its own bar.

		Args:
			key: Stable identifier of the value, used to keep its spring. str.
			label: Name shown at the left. str.
			subtitle: Second line under the name, empty when there is none. str.
			percent: Share already used, 0 to 100. float.
			y: Vertical cursor in device pixels. float.
			min_height: Smallest height the row may take, in layout units. float.

		Returns:
			float: The vertical cursor at the bottom of the row.
		"""
		pad = self._unit(PANEL_PAD)
		right = self._unit(PANEL_WIDTH) - pad
		items = [self._text((pad, y), label, "row", LABEL_PRIMARY, width=self._unit(LABEL_COLUMN_WIDTH))]
		if subtitle:
			items.append(
				self._text(
					(pad, y + self._unit(SUBTITLE_OFFSET)),
					subtitle,
					"caption",
					LABEL_SECONDARY,
					width=self._unit(LABEL_COLUMN_WIDTH),
				)
			)

		height = max(self._canvas.bbox(*items)[3] - y, self._unit(min_height))
		center = y + height / 2.0
		half_bar = self._unit(BAR_HEIGHT) / 2.0
		self._bar(
			(
				self._unit(BAR_COLUMN_LEFT),
				center - half_bar,
				right - self._unit(VALUE_COLUMN_WIDTH),
				center + half_bar,
			),
			key,
			percent / 100.0,
			percent,
		)
		self._text((right, center), format_percent(percent), "row_value", LABEL_SECONDARY, anchor="e")
		return y + height

	def _draw_section_title(self, title: str, y: float) -> float:
		"""Draw a section heading and return the vertical cursor after it.

		Args:
			title: The heading text. str.
			y: Vertical cursor in device pixels. float.

		Returns:
			float: The vertical cursor after the heading.
		"""
		self._text((self._unit(PANEL_PAD), y), title, "section", LABEL_PRIMARY)
		return y + self._unit(SECTION_TITLE_GAP)

	def _tick_status(self) -> None:
		"""Rewrite the countdown once a second while the panel is open.

		The countdown is the one thing on the panel that changes without a new
		reading, so it is refreshed on its own timer rather than at every frame.

		Returns:
			None.
		"""
		self._status_job = None
		if not self._visible:
			return
		if self._status_item:
			self._canvas.itemconfigure(self._status_item, text=self._status_text())
		self._status_job = self._window.after(STATUS_INTERVAL_MS, self._tick_status)

	def _draw_footer(self, y: float) -> float:
		"""Draw the line counting down to the next reading.

		A reading in flight adds a spinner on the right: the wait is over and the
		work is what is happening now.

		Args:
			y: Vertical cursor in device pixels. float.

		Returns:
			float: The vertical cursor after the footer.
		"""
		pad = self._unit(PANEL_PAD)
		right = self._unit(PANEL_WIDTH) - pad

		self._status_item = self._text(
			(pad, y),
			self._status_text(),
			"caption",
			LABEL_SECONDARY,
			width=self._unit(PANEL_WIDTH - 2 * PANEL_PAD),
		)

		if self._sign_in_link:
			# The address takes the place of the countdown's trailing space: a
			# sign-in is in front of the reading, not beside it.
			self._spinner_item = 0
			return self._draw_sign_in_link(self._canvas.bbox(self._status_item)[3])

		if self._refreshing:
			size = self._unit(SPINNER_SIZE)
			self._spinner_item = self._canvas.create_arc(
				right - size,
				y,
				right,
				y + size,
				start=self._spinner_angle,
				extent=SPINNER_EXTENT,
				style="arc",
				outline=self._provider.accent,
				width=max(1.0, self._unit(SPINNER_STROKE)),
				tags="content",
			)
		else:
			self._spinner_item = 0
		return y + self._unit(20)

	def _draw_body(self, y: float) -> float:
		"""Draw every usage row of the stored reading.

		Args:
			y: Vertical cursor in device pixels. float.

		Returns:
			float: The vertical cursor after the last row.
		"""
		if self._snapshot is None:
			return y

		now = datetime.now(timezone.utc)
		for window in self._snapshot.windows():
			y = self._draw_row(
				f"limit:{window.key}",
				window.label,
				format_subtitle(window, now),
				window.percent,
				y,
				LIMIT_ROW_MIN_HEIGHT,
			)
			y += self._unit(LIMIT_ROW_GAP)

		if self._snapshot.breakdown:
			y = self._draw_section_title(PRODUCT_SECTION_TITLE, y + self._unit(6))
			for row in self._snapshot.breakdown:
				y = self._draw_row(
					f"{PRODUCT_KEY_PREFIX}{row.key}",
					row.label,
					"",
					row.percent,
					y,
					PRODUCT_ROW_MIN_HEIGHT,
				)
				y += self._unit(PRODUCT_ROW_GAP)

		if self._snapshot.extra_label and self._snapshot.extra_percent is not None:
			y = self._draw_section_title(self._snapshot.extra_label, y + self._unit(6))
			y = self._draw_row(
				"extra",
				self._snapshot.extra_label,
				"",
				self._snapshot.extra_percent,
				y,
				PRODUCT_ROW_MIN_HEIGHT,
			)
			y += self._unit(PRODUCT_ROW_GAP)
		return y

	def _font_pixels(self, style: str) -> int:
		"""Return the pixel size of a named text style on this display.

		Tk sizes fonts in points and Pillow in pixels, so text drawn by Pillow has
		to be converted before it will match the text beside it.

		Args:
			style: A key of the theme text styles, such as "caption_strong". str.

		Returns:
			int: The size in device pixels, at least 1.
		"""
		return max(1, int(round(text_style(style)[1] * self._scale * PIXELS_PER_POINT)))

	def _font(self, style: str) -> tkfont.Font:
		"""Return the font of a named text style, made once and kept.

		Tk is asked for the metrics of a face and for the width of text set in
		it, and both cost a round trip, so the object that asks is not remade
		every time something needs measuring.

		Args:
			style: A key of the theme text styles, such as "title". str.

		Returns:
			tkinter.font.Font: The font.
		"""
		specification = text_style(style)
		font = self._fonts.get(specification)
		if font is None:
			font = tkfont.Font(root=self._window, font=specification)
			self._fonts[specification] = font
		return font

	def _ascent(self, style: str) -> int:
		"""Return how far a named text style reaches above its baseline.

		Args:
			style: A key of the theme text styles, such as "title". str.

		Returns:
			int: The ascent in device pixels.
		"""
		specification = text_style(style)
		ascent = self._ascents.get(specification)
		if ascent is None:
			ascent = self._font(style).metrics("ascent")
			self._ascents[specification] = ascent
		return ascent

	def _fit(self, text: str, style: str, width: float) -> str:
		"""Return text cut short with an ellipsis until it fits a width.

		Tk draws canvas text whole or wrapped, never cut, so text that must stay
		on one line inside a given room is shortened here before it is drawn.

		Args:
			text: The text to fit. str.
			style: The style it will be set in, such as "row". str.
			width: The room available in device pixels. float.

		Returns:
			str: The text unchanged when it fits, as much of its start as fits
			followed by an ellipsis when it does not, or an empty string when
			not even one character and the ellipsis do.
		"""
		require_type(text, str, "text")
		font = self._font(style)
		if font.measure(text) <= width:
			return text
		for length in range(len(text) - 1, 0, -1):
			shortened = text[:length] + ELLIPSIS
			if font.measure(shortened) <= width:
				return shortened
		return ""

	def _draw_header(self, y: float) -> float:
		"""Draw the provider mark, its name, and the plan name beside the name.

		Args:
			y: Vertical cursor in device pixels. float.

		Returns:
			float: The vertical cursor after the row.
		"""
		pad = self._unit(PANEL_PAD)
		logo_size = max(1, int(round(self._unit(LOGO_SIZE))))
		self._logo_photo = ImageTk.PhotoImage(
			render_logo(self._provider.logo_file, logo_size, self._provider.accent)
		)
		self._canvas.create_image(pad, y + self._unit(2), image=self._logo_photo, anchor="nw", tags="content")
		title = self._text(
			(pad + logo_size + self._unit(LOGO_TITLE_GAP), y),
			self._provider.label,
			"title",
			LABEL_PRIMARY,
		)

		if self._snapshot is not None:
			# Both runs are anchored by the top of their line box, so sitting the
			# smaller one lower by the difference in ascent puts the two on one
			# baseline. Matching the bottoms instead would drop it, because a
			# smaller face reserves less room under the baseline.
			title_right = self._canvas.bbox(title)[2]
			self._text(
				(title_right + self._unit(PLAN_GAP), y + self._ascent("title") - self._ascent("caption_strong")),
				self._snapshot.plan,
				"caption_strong",
				LABEL_TERTIARY,
			)

		size = self._control_size()
		self._draw_control(
			lambda color: render_gear(size, color),
			self._unit(PANEL_WIDTH) - pad - size,
			self._glyph_top(y, "title", size),
			GEAR_KEY,
		)
		return self._canvas.bbox(title)[3] + self._unit(HEADER_GAP)

	def _text_middle(self, y: float, style: str) -> float:
		"""Return where the capitals of one line of text are centered.

		Anything set beside a line of text is centered on this rather than on the
		line box Tk reports, which reserves room under the baseline for
		descenders the line may not have and would leave the neighbour low.

		Args:
			y: Top of the text run in device pixels, as it was anchored. float.
			style: The text style the run is set in, such as "title". str.

		Returns:
			float: The middle of the capitals, in device pixels.
		"""
		return y + self._ascent(style) - self._font_pixels(style) * CAP_HEIGHT_RATIO / 2.0

	def _glyph_top(self, y: float, style: str, glyph_height: int) -> float:
		"""Return where a mark must start to center on a run of text.

		Args:
			y: Top of the text run in device pixels, as it was anchored. float.
			style: The text style the run is set in, such as "title". str.
			glyph_height: Height of the mark in device pixels. int.

		Returns:
			float: The top edge of the mark, in device pixels.
		"""
		return self._text_middle(y, style) - glyph_height / 2.0

	def _control_size(self) -> int:
		"""Return the edge length of the gear on this display.

		Returns:
			int: The size in device pixels, at least 1.
		"""
		return max(1, int(round(self._unit(CONTROL_SIZE))))

	def _back_size(self) -> int:
		"""Return the height of the back chevron on this display.

		Returns:
			int: The height in device pixels, at least 1.
		"""
		return max(1, int(round(self._control_size() * BACK_SIZE_RATIO)))

	def _add_hit(self, box: tuple[float, float, float, float], key: str) -> None:
		"""Register the area that answers to a click, in unscrolled coordinates.

		Args:
			box: The area as (left, top, right, bottom) in device pixels, as it
				stands with the content at the top of its scroll. tuple of four
				floats.
			key: What to report when the area is clicked. str, non-empty.

		Returns:
			None.
		"""
		require_non_empty_str(key, "key")
		self._hits.append((box, key))

	def _draw_control(
		self,
		render: Callable[[str], Image.Image],
		left: float,
		top: float,
		key: str,
	) -> None:
		"""Place one mark that can be clicked, in both the colors it is drawn in.

		A mark under the pointer turns the color of the service, which is the
		same answer the switch and the spinner give. Both colors are rendered now
		and swapped later, because the pointer moving is not a reason to redraw
		the panel.

		Args:
			render: Takes a color and returns the mark in it. Callable taking one
				str and returning a PIL.Image.Image in mode "RGBA".
			left: Position of the mark's left edge in device pixels. float.
			top: Position of its top edge in device pixels. float.
			key: What to report when it is clicked. str, non-empty.

		Returns:
			None.
		"""
		if not callable(render):
			raise TypeError("render must be callable")
		require_non_empty_str(key, "key")

		resting = ImageTk.PhotoImage(render(LABEL_SECONDARY))
		lit = ImageTk.PhotoImage(render(self._provider.accent))
		# Kept on the panel because Tk holds only a weak reference to the image
		# behind a canvas item, and a collected photo leaves a blank space.
		self._control_photos.extend((resting, lit))
		item = self._canvas.create_image(left, top, image=resting, anchor="nw", tags="content")
		self._lit[key] = lambda on: self._canvas.itemconfigure(item, image=lit if on else resting)

		reach = self._unit(CONTROL_HIT_PAD)
		self._add_hit(
			(left - reach, top - reach, left + resting.width() + reach, top + resting.height() + reach),
			key,
		)

	def _draw_action(self, text: str, right: float, middle: float, key: str) -> float:
		"""Draw a word that answers to a click, and return where it begins.

		Args:
			text: The word, such as "Sign out". str, non-empty.
			right: Where its right hand edge sits, in device pixels. float.
			middle: The line it is centered on, in device pixels. float.
			key: What to report when it is clicked. str, non-empty.

		Returns:
			float: The left edge of the word in device pixels, which is what is
			left for whatever goes beside it.
		"""
		require_non_empty_str(text, "text")
		require_non_empty_str(key, "key")

		item = self._text((right, middle), text, "row", LABEL_SECONDARY, anchor="e")
		accent = self._provider.accent
		self._lit[key] = lambda on: self._canvas.itemconfigure(item, fill=accent if on else LABEL_SECONDARY)

		left, top, edge, bottom = self._canvas.bbox(item)
		reach = self._unit(ACTION_HIT_PAD)
		self._add_hit((left - reach, top - reach, edge + reach, bottom + reach), key)
		return float(left)

	def _set_hovered(self, key: str) -> None:
		"""Color whatever the pointer is over, and put back what it left.

		Args:
			key: Key of the thing under the pointer, empty for none. str.

		Returns:
			None.
		"""
		if key == self._hovered:
			return
		for candidate, light in self._lit.items():
			light(candidate == key)
		self._hovered = key

	def _draw_settings_header(self, y: float) -> float:
		"""Draw the chevron back to the reading, and the title beside it.

		Args:
			y: Vertical cursor in device pixels. float.

		Returns:
			float: The vertical cursor after the row.
		"""
		pad = self._unit(PANEL_PAD)
		size = self._back_size()
		chevron = render_back(size, LABEL_SECONDARY)
		title = self._text(
			(pad + chevron.width + self._unit(LOGO_TITLE_GAP), y),
			SETTINGS_TITLE,
			"title",
			LABEL_PRIMARY,
		)
		self._draw_control(
			lambda color: render_back(size, color),
			pad,
			self._glyph_top(y, "title", chevron.height),
			BACK_KEY,
		)
		return self._canvas.bbox(title)[3] + self._unit(HEADER_GAP)

	def _draw_settings(self, y: float) -> float:
		"""Draw every setting: the switch that starts the widget, and the folder.

		Args:
			y: Vertical cursor in device pixels. float.

		Returns:
			float: The vertical cursor after the last setting.
		"""
		y = self._draw_startup_row(y) + self._unit(SETTINGS_ROW_GAP)
		return self._draw_sign_in_link(self._draw_account_row(y))

	def _draw_settings_label(self, label: str, y: float, control_height: float) -> tuple[float, float]:
		"""Draw the name of one setting and return the line its control sits on.

		The name and its control are centered on one line, the way a usage row
		centers its bar against the name of its limit, so a row reads as one line
		however tall the control beside it is. The names are single lines, which
		is what lets the name be moved onto the middle of the row once the row
		has been measured.

		Args:
			label: Name of the setting, which is one line. str, non-empty.
			y: Vertical cursor in device pixels. float.
			control_height: Height of the control going beside it, in device
				pixels. float.

		Returns:
			tuple[float, float]: The middle of the row and its height, both in
			device pixels.
		"""
		require_non_empty_str(label, "label")
		require_type(control_height, (int, float), "control_height")

		name = self._text((self._unit(PANEL_PAD), y), label, "row", LABEL_PRIMARY)
		height = max(
			self._canvas.bbox(name)[3] - y,
			float(control_height),
			self._unit(SETTINGS_ROW_MIN_HEIGHT),
		)
		middle = y + height / 2.0
		self._canvas.move(name, 0, middle - self._text_middle(y, "row"))
		return (middle, height)

	def _draw_startup_row(self, y: float) -> float:
		"""Draw the name of the startup setting and the switch that sets it.

		Args:
			y: Vertical cursor in device pixels. float.

		Returns:
			float: The vertical cursor at the bottom of the row.
		"""
		right = self._unit(PANEL_WIDTH) - self._unit(PANEL_PAD)
		width = self._unit(SWITCH_WIDTH)
		switch_height = self._unit(SWITCH_HEIGHT)
		middle, height = self._draw_settings_label(STARTUP_LABEL, y, switch_height)

		# On, the switch is the color of the service, which is what marks the
		# panel as belonging to it.
		self._switch = Switch(
			self._canvas,
			(right - width, middle - switch_height / 2.0, right, middle + switch_height / 2.0),
			mix_hex(SURFACE_BASE, LABEL_PRIMARY, SWITCH_OFF_OPACITY),
			self._provider.accent,
			"content",
		)
		self._switch.set_fraction(1.0 if self._start_on_startup else 0.0)
		self._add_hit(self._switch.box, STARTUP_KEY)
		return y + height

	def _draw_account_row(self, y: float) -> float:
		"""Draw who is signed in, and the word that changes that.

		The name is set under the label on a line of its own rather than squeezed
		between the label and the word, because an email address is as long as it
		is and the panel is not going to widen for it.

		Args:
			y: Vertical cursor in device pixels. float.

		Returns:
			float: The vertical cursor at the bottom of the row.
		"""
		pad = self._unit(PANEL_PAD)
		right = self._unit(PANEL_WIDTH) - pad

		label = self._text((pad, y), ACCOUNT_LABEL, "row", LABEL_PRIMARY)
		action = SIGN_OUT_LABEL if self._signed_in else SIGN_IN_LABEL
		self._draw_action(action, right, self._text_middle(y, "row"), ACCOUNT_KEY)

		name = self._account if self._signed_in and self._account else NOT_SIGNED_IN_LABEL
		room = self._unit(PANEL_WIDTH - 2 * PANEL_PAD)
		caption = self._text(
			(pad, self._canvas.bbox(label)[3] + self._unit(SETTINGS_CAPTION_GAP)),
			self._fit(name, "caption", room),
			"caption",
			LABEL_SECONDARY,
		)
		return float(self._canvas.bbox(caption)[3])

	def _draw_sign_in_link(self, y: float) -> float:
		"""Draw the address a sign-in is waiting at, when there is one.

		Drawn in the provider's own color, and underlined under the pointer,
		which is what marks it as somewhere to go rather than something to read.
		It is here because a browser that will not open should not be the end of
		a sign-in: the address is on screen either way.

		Args:
			y: Vertical cursor in device pixels. float.

		Returns:
			float: The vertical cursor after the link, unchanged when there is
			no address to offer.
		"""
		if not self._sign_in_link:
			return y

		pad = self._unit(PANEL_PAD)
		room = self._unit(PANEL_WIDTH - 2 * PANEL_PAD)
		y += self._unit(LINK_GAP)

		item = self._text(
			(pad, y),
			self._fit(self._sign_in_link, "caption", room),
			"caption",
			self._provider.accent,
		)
		plain = text_style("caption")
		underlined = plain + ("underline",)
		self._lit[SIGN_IN_LINK_KEY] = lambda on: self._canvas.itemconfigure(
			item, font=underlined if on else plain
		)

		left, top, right, bottom = self._canvas.bbox(item)
		reach = self._unit(ACTION_HIT_PAD)
		self._add_hit((left - reach, top - reach, right + reach, bottom + reach), SIGN_IN_LINK_KEY)

		y = bottom + self._unit(LINK_CAPTION_GAP)
		self._link_caption_item = self._text((pad, y), "", "caption", LABEL_SECONDARY, width=room)
		return y + self._unit(SUBTITLE_OFFSET)

	def _open_sign_in_link(self) -> None:
		"""Put the sign-in address on the clipboard and ask for it to be opened.

		Both, and in that order. The reason the address is on screen at all is
		that a browser may refuse to open, and a click cannot make it open
		either; what a click can always do is leave the address somewhere the
		user can paste it.

		Returns:
			None.
		"""
		if not self._sign_in_link:
			return
		try:
			self._window.clipboard_clear()
			self._window.clipboard_append(self._sign_in_link)
		except tk.TclError:
			# No clipboard to write to, which costs the paste and nothing else.
			pass
		if self._link_caption_item:
			self._canvas.itemconfigure(self._link_caption_item, text=LINK_COPIED_TEXT)
		self._on_open_sign_in()

	def _rebuild(self) -> None:
		"""Redraw the whole panel, in whichever view it is showing.

		Returns:
			None.
		"""
		# The pointer does not move because the panel redrew, so whatever it was
		# over is put back over the mark that has replaced it.
		hovered = self._hovered
		self._canvas.delete("content")
		self._bars.clear()
		self._hits.clear()
		self._lit.clear()
		self._control_photos.clear()
		self._hovered = ""
		self._switch = None
		self._link_caption_item = 0
		self._scroll_offset = 0.0

		pad = self._unit(PANEL_PAD)
		if self._view == SETTINGS_VIEW:
			# Neither belongs to this view, and both are stepped on every frame
			# while they are set, so they are cleared rather than left pointing
			# at items that have just been deleted.
			self._status_item = 0
			self._spinner_item = 0
			self._content_height = self._draw_settings(self._draw_settings_header(pad)) + pad
		else:
			y = self._draw_body(self._draw_header(pad))
			self._content_height = self._draw_footer(y + self._unit(4)) + pad
			self._usage_height = self._content_height
		self._set_hovered(hovered if hovered in self._lit else "")

	def _hit_at(self, x: float, y: float) -> str:
		"""Return the key of whatever sits under a point.

		Args:
			x: Position across the canvas in device pixels. float.
			y: Position down the canvas in device pixels, with the scroll offset
				already taken off. float.

		Returns:
			str: The key of the area under the point, or an empty string when
			nothing there answers to a click.
		"""
		for (left, top, right, bottom), key in self._hits:
			if left <= x <= right and top <= y <= bottom:
				return key
		return ""

	def _on_click(self, event: tk.Event) -> None:
		"""Act on a click that lands on anything that answers to one.

		Args:
			event: The button event. tkinter.Event.

		Returns:
			None. A click that lands anywhere else does nothing.
		"""
		key = self._hit_at(event.x, event.y - self._scroll_offset)
		if key == GEAR_KEY:
			self._set_view(SETTINGS_VIEW)
		elif key == BACK_KEY:
			self._set_view(USAGE_VIEW)
		elif key == STARTUP_KEY:
			self._toggle_startup()
		elif key == ACCOUNT_KEY:
			# The panel is left open. A browser that opens takes the focus and
			# dismisses it anyway, and one that does not leaves the panel in
			# front of the user with the address to open by hand.
			if self._signed_in:
				self._on_sign_out()
			else:
				self._on_sign_in()
		elif key == SIGN_IN_LINK_KEY:
			self._open_sign_in_link()

	def _on_leave(self, _event: tk.Event) -> None:
		"""Put back whatever the pointer was over when it leaves the panel.

		Args:
			_event: The leave event, which carries nothing needed here.
				tkinter.Event.

		Returns:
			None.
		"""
		self._canvas.configure(cursor="")
		self._set_hovered("")

	def _on_motion(self, event: tk.Event) -> None:
		"""Show the hand pointer over anything that answers to a click.

		Args:
			event: The motion event. tkinter.Event.

		Returns:
			None.
		"""
		over = self._hit_at(event.x, event.y - self._scroll_offset)
		self._canvas.configure(cursor="hand2" if over else "")
		self._set_hovered(over if over in self._lit else "")

	def _set_view(self, view: str) -> None:
		"""Show one of the two views, redrawing and resizing the panel for it.

		Args:
			view: Either USAGE_VIEW or SETTINGS_VIEW. str.

		Returns:
			None. Asking for the view already showing does nothing.
		"""
		require_member(view, PANEL_VIEWS, "view")
		if view == self._view:
			return
		self._view = view
		self._layout()
		self._start_animating()

	def _toggle_startup(self) -> None:
		"""Turn the start on startup switch over and report the new value.

		The switch is redrawn before the value is reported, so it answers the
		click at once rather than after whatever the owner does with it.

		Returns:
			None.
		"""
		self._start_on_startup = not self._start_on_startup
		if self._switch is not None:
			self._switch.set_fraction(1.0 if self._start_on_startup else 0.0)
		self._on_startup_change(self._start_on_startup)

	def _scroll_to(self, offset: float, viewport_height: float) -> None:
		"""Move the drawn content to a scroll offset, clamped to what is scrollable.

		Args:
			offset: Wanted offset in device pixels, 0 at the top and negative
				further down. float.
			viewport_height: Height of the visible area in device pixels. float.

		Returns:
			None.
		"""
		overflow = max(0.0, self._content_height - viewport_height)
		wanted = min(0.0, max(-overflow, offset))
		self._canvas.move("content", 0, wanted - self._scroll_offset)
		self._scroll_offset = wanted

	def _on_mouse_wheel(self, event: tk.Event) -> None:
		"""Scroll the panel when its content is taller than the window.

		Args:
			event: The wheel event, whose delta is a multiple of 120 on Windows.
				tkinter.Event.

		Returns:
			None.
		"""
		self._scroll_to(self._scroll_offset + event.delta / 120.0 * self._unit(48), self._canvas.winfo_height())

	def _on_frame(self, dt: float) -> bool:
		"""Advance every spring and the spinner by one frame.

		Args:
			dt: Length of the frame in seconds. float.

		Returns:
			bool: True while anything is still moving.
		"""
		for bar, spring in self._bars:
			bar.set_fraction(min(1.0, max(0.0, spring.step(dt))))

		if self._spinner_item:
			self._spinner_angle = (self._spinner_angle - SPINNER_DEGREES_PER_SECOND * dt) % 360.0
			self._canvas.itemconfigure(self._spinner_item, start=self._spinner_angle)
		settling = any(not spring.settled for _bar, spring in self._bars)
		return settling or bool(self._spinner_item)

	def _layout(self) -> None:
		"""Size the panel to the reading and park it above the notification area.

		Both views get the height the reading needs, so opening the settings and
		coming back does not resize the window under the pointer. The settings
		are shorter than the reading and simply leave space below them, except
		before the first reading has been taken, when the reading is one line and
		the settings are what set the height.

		Returns:
			None.
		"""
		self._window.update_idletasks()
		self._scale = self._window.winfo_fpixels("1i") / 96.0
		previous_offset = self._scroll_offset
		if self._view == SETTINGS_VIEW and not self._usage_height:
			# Opened straight into the settings from the menu, so the reading has
			# never been drawn and its height is not known yet. Drawing it once
			# and throwing it away is what gives the window its usual size.
			self._view = USAGE_VIEW
			self._rebuild()
			self._view = SETTINGS_VIEW
		self._rebuild()

		left, top, right, bottom = work_area(
			self._window.winfo_screenwidth(),
			self._window.winfo_screenheight(),
		)
		width = int(round(self._unit(PANEL_WIDTH)))
		margin = int(round(self._unit(SCREEN_MARGIN)))
		# Never shorter than what has just been drawn, so a reading that has not
		# arrived yet cannot leave the settings cut off below the window.
		wanted = max(self._usage_height, self._content_height)
		height = int(round(min(wanted, (bottom - top) - 2 * margin)))

		x = max(left, right - width - margin)
		y = max(top, bottom - height - margin)
		self._canvas.configure(width=width, height=height)
		self._window.geometry(f"{width}x{height}+{x}+{y}")
		self._scroll_to(previous_offset, height)

	def update_view(self, snapshot: UsageSnapshot | None, sign_in_message: str, refreshing: bool) -> None:
		"""Store the latest reading and redraw the panel if it is open.

		A failed attempt leaves the previous reading in place. Unless it is one
		the user can fix by signing in, nothing is said about it and the age of
		what is on screen carries the news.

		Args:
			snapshot: The most recent successful reading, or None when there has
				never been one. UsageSnapshot or None.
			sign_in_message: What the user should run to sign in again, empty when
				the sign-in is fine. str.
			refreshing: Whether a reading is in flight, which puts a spinner in
				the footer. bool.

		Returns:
			None.
		"""
		if snapshot is not None:
			require_type(snapshot, UsageSnapshot, "snapshot")
		require_type(sign_in_message, str, "sign_in_message")
		require_type(refreshing, bool, "refreshing")

		self._snapshot = snapshot
		self._sign_in_message = sign_in_message
		self._refreshing = refreshing
		if self._visible:
			self._layout()
			self._start_animating()

	def set_startup(self, enabled: bool) -> None:
		"""Set which way the start on startup switch is drawn.

		Called by the owner with the stored preference, so the switch shows what
		is actually in force rather than its own default.

		Args:
			enabled: Whether the widget starts with Windows. bool.

		Returns:
			None.
		"""
		require_type(enabled, bool, "enabled")
		self._start_on_startup = enabled
		if self._visible:
			self._layout()

	def set_account(self, account: str, signed_in: bool) -> None:
		"""Set who the settings say is signed in.

		Args:
			account: Who is signed in, as they should be named. Empty when the
				sign-in reported no name for them. str.
			signed_in: Whether there is a sign-in at all, which is what decides
				whether the row offers to sign out or to sign in. bool.

		Returns:
			None.
		"""
		require_type(account, str, "account")
		require_type(signed_in, bool, "signed_in")
		self._account = account
		self._signed_in = signed_in
		if self._visible and self._view == SETTINGS_VIEW:
			self._layout()

	def set_sign_in_link(self, address: str) -> None:
		"""Offer an address to sign in at, or withdraw the offer.

		Args:
			address: The address, empty when no sign-in is under way. str.

		Returns:
			None.
		"""
		require_type(address, str, "address")
		if address == self._sign_in_link:
			return
		self._sign_in_link = address
		if self._visible:
			self._layout()

	@property
	def visible(self) -> bool:
		"""Return whether the panel is on screen or on its way there.

		Returns:
			bool: True from the moment it starts appearing until it has finished
			dismissing.
		"""
		return self._visible

	def _window_handle(self) -> int:
		"""Return the native handle of the panel window.

		Returns:
			int: The handle of the window manager frame, or of the Tk window
			itself when the frame is not reported.
		"""
		frame = self._window.frame()
		return int(frame, 16) if frame else self._window.winfo_id()

	def show(self, view: str = USAGE_VIEW) -> None:
		"""Present the panel above the notification area and give it focus.

		Args:
			view: Which view to open on, either USAGE_VIEW or SETTINGS_VIEW. The
				panel always opens on the view asked for rather than the one it
				was left in, so dismissing it and clicking an icon comes back to
				the reading. str.

		Returns:
			None.
		"""
		require_member(view, PANEL_VIEWS, "view")
		self._view = view
		self._layout()
		for bar, spring in self._bars:
			spring.rewind(0.0)
			bar.set_fraction(0.0)
		self._window.deiconify()
		apply_panel_chrome(self._window_handle())
		self._window.lift()
		self._window.focus_force()
		self._visible = True
		self._tick_status()
		self._start_animating()

	def hide(self) -> None:
		"""Take the panel off screen.

		Returns:
			None.
		"""
		if not self._visible:
			return
		self._visible = False
		if self._status_job is not None:
			self._window.after_cancel(self._status_job)
			self._status_job = None
		self._ticker.stop()
		self._window.withdraw()
		self._hidden_at = time.monotonic()

	def dismissed_by_this_click(self) -> bool:
		"""Return whether the panel went away just now, as part of the current click.

		Returns:
			bool: True when it was hidden within the last CLICK_DISMISS_SECONDS.
		"""
		return not self._visible and (time.monotonic() - self._hidden_at) < CLICK_DISMISS_SECONDS

	def _start_animating(self) -> None:
		"""Run the frame loop, or jump to the end when motion is turned off.

		Every redraw goes through here, because a redraw rebuilds the bars at
		whatever their springs have reached and something has to carry them the
		rest of the way.

		Returns:
			None.
		"""
		if animations_enabled():
			self._ticker.start()
		else:
			self._settle_immediately()

	def _settle_immediately(self) -> None:
		"""Put every animated value at its target without animating.

		Returns:
			None.
		"""
		for bar, spring in self._bars:
			spring.jump_to(spring.target)
			bar.set_fraction(min(1.0, max(0.0, spring.value)))
