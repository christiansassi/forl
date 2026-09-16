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
"""

from __future__ import annotations

import time
import tkinter as tk
from datetime import datetime, timezone
from PIL import ImageTk

from ..providers import Provider
from ..render.logo import render_logo
from ..render.theme import (
	LABEL_PRIMARY,
	LABEL_SECONDARY,
	LABEL_TERTIARY,
	SURFACE_BASE,
	text_style,
	track_hex,
	usage_hex,
)
from ..usage.snapshot import PRODUCT_KEY_PREFIX, UsageSnapshot, now_utc
from ..validation import require_non_empty_str, require_positive_int, require_type
from .animation import Spring, Ticker
from .capsule_bar import CapsuleBar
from .desktop import animations_enabled, apply_panel_chrome, work_area
from .formatting import format_next_update, format_percent, format_subtitle

PANEL_WIDTH = 430
PANEL_PAD = 20
SCREEN_MARGIN = 10

LABEL_COLUMN_WIDTH = 176
BAR_COLUMN_LEFT = 206
VALUE_COLUMN_WIDTH = 46
BAR_HEIGHT = 5

LOGO_SIZE = 17
LOGO_TITLE_GAP = 9

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

BAR_RESPONSE = 0.45

PRODUCT_SECTION_TITLE = "This week's usage by product"
LOADING_TEXT = "Loading"
STATUS_INTERVAL_MS = 1000

# Clicking a tray icon takes focus away from the panel, which dismisses it
# before the click is delivered. A dismissal this recent is treated as part of
# that click, so the click closes the panel instead of closing and reopening it.
CLICK_DISMISS_SECONDS = 0.4


class Panel:
	"""A hidden-by-default flyout showing every usage the account reports."""

	def __init__(self, master: tk.Tk, provider: Provider, poll_seconds: int) -> None:
		"""Create the panel as a hidden child of the application root window.

		Args:
			master: The application root window. tkinter.Tk.
			provider: The service being reported on, which names and colors the
				panel. Provider.
			poll_seconds: Delay between readings, which is how long the dial in
				the footer takes to come round. int, greater than 0.

		Returns:
			None.
		"""
		require_type(master, tk.Tk, "master")
		require_type(provider, Provider, "provider")
		require_positive_int(poll_seconds, "poll_seconds")

		self._provider = provider
		self._poll_seconds = poll_seconds
		self._visible = False
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
		self._spinner_angle = 90.0
		self._scale = 1.0
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

	def _status_text(self) -> str:
		"""Return the line describing how fresh the reading is.

		A failure the user can do something about, which means signing in again,
		is the one thing worth saying and it takes the line. A failure they
		cannot, such as a busy endpoint, is not reported at all: the reading on
		screen is still the last good one and its age says the rest.

		Returns:
			str: The sign-in instruction when there is one, otherwise the countdown
			to the next reading, or "Loading" before the first one.
		"""
		if self._sign_in_message:
			return self._sign_in_message
		if self._snapshot is None:
			return LOADING_TEXT
		return format_next_update(self._seconds_to_next_update())

	def _seconds_to_next_update(self) -> float:
		"""Return how long is left before the next reading is taken.

		Returns:
			float: Seconds remaining, 0 once the reading is due and 0 when there
			has never been one.
		"""
		if self._snapshot is None:
			return 0.0
		elapsed = (now_utc() - self._snapshot.fetched_at).total_seconds()
		return max(0.0, self._poll_seconds - elapsed)

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

	def _rebuild(self) -> None:
		"""Redraw the whole panel from the stored reading.

		Returns:
			None.
		"""
		self._canvas.delete("content")
		self._bars.clear()
		self._scroll_offset = 0.0

		pad = self._unit(PANEL_PAD)
		y = pad
		logo_size = max(1, int(round(self._unit(LOGO_SIZE))))
		self._logo_photo = ImageTk.PhotoImage(
			render_logo(self._provider.logo_file, logo_size, self._provider.accent)
		)
		self._canvas.create_image(pad, y + self._unit(2), image=self._logo_photo, anchor="nw", tags="content")
		self._text(
			(pad + logo_size + self._unit(LOGO_TITLE_GAP), y),
			self._provider.label,
			"title",
			LABEL_PRIMARY,
		)
		if self._snapshot is not None:
			self._text(
				(self._unit(PANEL_WIDTH) - pad, y + self._unit(3)),
				self._snapshot.plan,
				"caption_strong",
				LABEL_TERTIARY,
				anchor="ne",
			)
		y += self._unit(32)

		y = self._draw_body(y)
		self._content_height = self._draw_footer(y + self._unit(4)) + pad

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
		"""Size the panel to its content and park it above the notification area.

		Returns:
			None.
		"""
		self._window.update_idletasks()
		self._scale = self._window.winfo_fpixels("1i") / 96.0
		previous_offset = self._scroll_offset
		self._rebuild()

		left, top, right, bottom = work_area(
			self._window.winfo_screenwidth(),
			self._window.winfo_screenheight(),
		)
		width = int(round(self._unit(PANEL_WIDTH)))
		margin = int(round(self._unit(SCREEN_MARGIN)))
		height = int(round(min(self._content_height, (bottom - top) - 2 * margin)))

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
			self._ticker.start()

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

	def show(self) -> None:
		"""Present the panel above the notification area and give it focus.

		Returns:
			None.
		"""
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

		if animations_enabled():
			self._ticker.start()
		else:
			self._settle_immediately()

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

	def _settle_immediately(self) -> None:
		"""Put every animated value at its target without animating.

		Returns:
			None.
		"""
		for bar, spring in self._bars:
			spring.jump_to(spring.target)
			bar.set_fraction(min(1.0, max(0.0, spring.value)))
