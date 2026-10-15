"""The menu that opens on a right click.

Windows draws the menu of a notification area icon itself, in the system style,
and the only way to change that is to draw it yourself. This is that: a window
built the same way as the panel, on one canvas, with the same surface, type and
rounded corners, so the two read as parts of one widget rather than as an
application and a system menu.

It behaves the way the menu it replaces did. It opens at the pointer, flipped so
it always lands inside the work area, it closes on a choice, on Escape, or when
it loses focus, and a choice is reported through a callback.

One menu serves every icon, so the colors are chosen each time it opens: the
palette of the app mode in force, and the accent of the service whose icon was
clicked.
"""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from typing import Callable

from PIL import ImageTk

from ..render.shapes import rounded_fill
from ..render.theme import DARK_PALETTE, Palette, mix_hex, readable_accent, text_style
from ..validation import require_non_empty_str, require_type
from ..system import apply_panel_chrome, work_area
from .core import SEPARATOR, MenuRow
from .palette import current_palette

# Proportions of the Windows 11 context menu: rows inset from the edge by the
# plate that lights under the pointer, text inset again from the plate, small
# corners on the plate, and a floor on the width so a menu of one short line
# reads as a menu rather than as a button.
ROW_HEIGHT = 32
PAD_Y = 4
HIGHLIGHT_INSET = 4
TEXT_INSET = 12
CHECK_COLUMN = 20
TRAILING_PAD = 24
MIN_WIDTH = 160
SEPARATOR_HEIGHT = 9
SCREEN_MARGIN = 6

HIGHLIGHT_OPACITY = 0.08
SEPARATOR_OPACITY = 0.12
HIGHLIGHT_RADIUS = 4

CHECK_MARK = "✓"


class TrayMenu:
	"""A menu drawn in the style of the panel rather than by Windows."""

	def __init__(self, master: tk.Tk, on_choose: Callable[[str], None]) -> None:
		"""Create the menu as a hidden child of the application root window.

		Args:
			master: The application root window. tkinter.Tk.
			on_choose: Called with the key of the line the user picked. Callable
				taking one str and returning None.

		Returns:
			None.
		"""
		require_type(master, tk.Tk, "master")
		if not callable(on_choose):
			raise TypeError("on_choose must be callable")

		self._palette: Palette = DARK_PALETTE
		self._accent = DARK_PALETTE.label_primary
		self._on_choose = on_choose
		self._rows: tuple[MenuRow, ...] = ()
		self._row_tops: list[tuple[float, float, str]] = []
		self._highlight_photo: ImageTk.PhotoImage | None = None
		self._highlight_item = 0
		self._scale = 1.0
		self._visible = False

		self._window = tk.Toplevel(master)
		self._window.withdraw()
		self._window.overrideredirect(True)
		self._window.attributes("-topmost", True)
		self._window.resizable(False, False)
		self._window.configure(background=self._palette.surface)
		self._window.bind("<Escape>", lambda _event: self.hide())
		self._window.bind("<FocusOut>", lambda _event: self.hide())

		self._canvas = tk.Canvas(
			self._window,
			background=self._palette.surface,
			highlightthickness=0,
			borderwidth=0,
		)
		self._canvas.pack(fill="both", expand=True)
		self._canvas.bind("<Motion>", self._on_motion)
		self._canvas.bind("<Leave>", lambda _event: self._highlight(None))
		self._canvas.bind("<Button-1>", self._on_click)

	def _unit(self, value: float) -> float:
		"""Return a layout distance converted from layout units to device pixels.

		Args:
			value: The distance in layout units. float.

		Returns:
			float: The distance in device pixels.
		"""
		return value * self._scale

	def _measure(self, rows: tuple[MenuRow, ...]) -> tuple[int, int]:
		"""Return the size the menu needs for a set of rows.

		Args:
			rows: The lines to be drawn. tuple of MenuRow.

		Returns:
			tuple[int, int]: The width and height in device pixels.
		"""
		font = tkfont.Font(root=self._window, font=text_style("row"))
		widest = max((font.measure(row.label) for row in rows if row.key != SEPARATOR), default=0)
		width = max(self._unit(MIN_WIDTH), self._text_left(rows) + widest + self._unit(TRAILING_PAD))
		height = self._unit(PAD_Y) * 2
		for row in rows:
			height += self._unit(SEPARATOR_HEIGHT if row.key == SEPARATOR else ROW_HEIGHT)
		return int(round(width)), int(round(height))

	def _text_left(self, rows: tuple[MenuRow, ...]) -> float:
		"""Return where the text of every row starts.

		Room for a check mark is left only when a row carries one, so a menu with
		nothing checked has its text at the inset every Windows menu uses rather
		than pushed across by an empty column.

		Args:
			rows: The lines to be drawn. tuple of MenuRow.

		Returns:
			float: Distance from the left edge of the menu in device pixels.
		"""
		column = CHECK_COLUMN if any(row.checked for row in rows) else 0
		return self._unit(HIGHLIGHT_INSET + TEXT_INSET + column)

	def _draw(self, width: int) -> None:
		"""Draw every row, and the highlight that will track the pointer.

		Args:
			width: Width of the menu in device pixels. int.

		Returns:
			None.
		"""
		self._canvas.delete("all")
		self._row_tops = []
		surface = self._palette.surface
		ink = self._palette.label_primary

		inset = self._unit(HIGHLIGHT_INSET)
		text_left = self._text_left(self._rows)
		self._highlight_photo = ImageTk.PhotoImage(
			rounded_fill(
				int(round(width - inset * 2)),
				int(round(self._unit(ROW_HEIGHT))),
				mix_hex(surface, ink, HIGHLIGHT_OPACITY),
				self._unit(HIGHLIGHT_RADIUS),
			)
		)
		self._highlight_item = self._canvas.create_image(inset, 0, image=self._highlight_photo, anchor="nw", state="hidden")

		y = self._unit(PAD_Y)
		for row in self._rows:
			if row.key == SEPARATOR:
				middle = y + self._unit(SEPARATOR_HEIGHT) / 2.0
				self._canvas.create_line(
					inset + self._unit(TEXT_INSET),
					middle,
					width - inset - self._unit(TEXT_INSET),
					middle,
					fill=mix_hex(surface, ink, SEPARATOR_OPACITY),
				)
				y += self._unit(SEPARATOR_HEIGHT)
				continue

			height = self._unit(ROW_HEIGHT)
			self._row_tops.append((y, y + height, row.key))
			if row.checked:
				self._canvas.create_text(
					inset + self._unit(TEXT_INSET + CHECK_COLUMN / 2.0),
					y + height / 2.0,
					text=CHECK_MARK,
					font=text_style("row"),
					fill=self._accent,
				)
			self._canvas.create_text(
				text_left,
				y + height / 2.0,
				text=row.label,
				font=text_style("row"),
				fill=ink,
				anchor="w",
			)
			y += height

	def _row_at(self, y: float) -> str:
		"""Return the key of the row under a vertical position.

		Args:
			y: Position in device pixels from the top of the menu. float.

		Returns:
			str: The key of the row, or an empty string when none is there.
		"""
		for top, bottom, key in self._row_tops:
			if top <= y < bottom:
				return key
		return ""

	def _highlight(self, key: str | None) -> None:
		"""Move the highlight onto a row, or take it off.

		Args:
			key: Key of the row to highlight, or None for none. str or None.

		Returns:
			None.
		"""
		for top, _bottom, candidate in self._row_tops:
			if candidate == key:
				self._canvas.coords(self._highlight_item, self._unit(HIGHLIGHT_INSET), top)
				self._canvas.itemconfigure(self._highlight_item, state="normal")
				return
		self._canvas.itemconfigure(self._highlight_item, state="hidden")

	def _on_motion(self, event: tk.Event) -> None:
		"""Follow the pointer with the highlight.

		Args:
			event: The motion event. tkinter.Event.

		Returns:
			None.
		"""
		self._highlight(self._row_at(event.y) or None)

	def _on_click(self, event: tk.Event) -> None:
		"""Report the chosen row and close.

		Args:
			event: The button event. tkinter.Event.

		Returns:
			None.
		"""
		key = self._row_at(event.y)
		self.hide()
		if key:
			self._on_choose(key)

	@property
	def visible(self) -> bool:
		"""Return whether the menu is on screen.

		Returns:
			bool: True while the menu is shown.
		"""
		return self._visible

	def show(self, rows: tuple[MenuRow, ...], pointer: tuple[int, int], accent: str) -> None:
		"""Draw the menu and open it at the pointer.

		The menu opens up and to the left of the pointer, the way a menu from the
		notification area does, and is pushed back inside the work area when that
		would take it off screen.

		Args:
			rows: The lines to draw, in order. tuple of MenuRow, non-empty.
			pointer: Where the pointer is as (x, y) in screen pixels. tuple of
				two ints.
			accent: Color of the service whose icon was clicked, which the check
				marks are drawn in, as a "#rrggbb" string. str, non-empty.

		Returns:
			None.
		"""
		require_type(rows, tuple, "rows")
		if not rows:
			raise ValueError("rows must not be empty")
		require_non_empty_str(accent, "accent")

		self._palette = current_palette()
		self._accent = readable_accent(accent, self._palette)
		self._window.configure(background=self._palette.surface)
		self._canvas.configure(background=self._palette.surface)
		self._window.update_idletasks()
		self._scale = self._window.winfo_fpixels("1i") / 96.0
		self._rows = rows
		width, height = self._measure(rows)
		self._draw(width)
		self._canvas.configure(width=width, height=height)

		left, top, right, bottom = work_area(
			self._window.winfo_screenwidth(),
			self._window.winfo_screenheight(),
		)
		margin = int(round(self._unit(SCREEN_MARGIN)))
		x = min(max(left + margin, pointer[0] - width), right - width - margin)
		y = min(max(top + margin, pointer[1] - height), bottom - height - margin)
		self._window.geometry(f"{width}x{height}+{x}+{y}")

		self._window.deiconify()
		apply_panel_chrome(self._window_handle(), self._palette.dark)
		self._window.lift()
		self._window.focus_force()
		self._highlight(None)
		self._visible = True

	def _window_handle(self) -> int:
		"""Return the native handle of the menu window.

		Returns:
			int: The handle of the window manager frame, or of the Tk window
			itself when the frame is not reported.
		"""
		frame = self._window.frame()
		return int(frame, 16) if frame else self._window.winfo_id()

	def hide(self) -> None:
		"""Take the menu off screen.

		Returns:
			None.
		"""
		if not self._visible:
			return
		self._visible = False
		self._window.withdraw()

