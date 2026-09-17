"""The menu that opens on a right click.

Windows draws the menu of a notification area icon itself, in the system style,
and the only way to change that is to draw it yourself. This is that: a window
built the same way as the panel, on one canvas, with the same surface, type and
rounded corners, so the two read as parts of one widget rather than as an
application and a system menu.

It behaves the way the menu it replaces did. It opens at the pointer, flipped so
it always lands inside the work area, it closes on a choice, on Escape, or when
it loses focus, and a choice is reported through a callback.
"""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from typing import Callable, NamedTuple

from PIL import ImageTk

from ..render.shapes import rounded_fill
from ..render.theme import LABEL_PRIMARY, LABEL_SECONDARY, SURFACE_BASE, mix_hex, text_style
from ..validation import require_non_empty_str, require_type
from ..system import apply_panel_chrome, work_area

ROW_HEIGHT = 30
CHECK_COLUMN = 24
PAD_X = 12
PAD_Y = 6
TRAILING_PAD = 28
SEPARATOR_HEIGHT = 9
SCREEN_MARGIN = 6

HIGHLIGHT_OPACITY = 0.10
SEPARATOR_OPACITY = 0.12
HIGHLIGHT_RADIUS = 6

CHECK_MARK = "✓"
SEPARATOR = "separator"


class MenuRow(NamedTuple):
	"""One line of the menu.

	Attributes:
		key: What to report when the line is chosen, or SEPARATOR for a rule. str.
		label: The text of the line, empty for a rule. str.
		checked: Whether the line carries a check mark. bool.
	"""

	key: str
	label: str
	checked: bool


class TrayMenu:
	"""A menu drawn in the style of the panel rather than by Windows."""

	def __init__(self, master: tk.Tk, accent: str, on_choose: Callable[[str], None]) -> None:
		"""Create the menu as a hidden child of the application root window.

		Args:
			master: The application root window. tkinter.Tk.
			accent: Color of the check marks, as a "#rrggbb" string. str, non-empty.
			on_choose: Called with the key of the line the user picked. Callable
				taking one str and returning None.

		Returns:
			None.
		"""
		require_type(master, tk.Tk, "master")
		require_non_empty_str(accent, "accent")
		if not callable(on_choose):
			raise TypeError("on_choose must be callable")

		self._accent = accent
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
		self._window.configure(background=SURFACE_BASE)
		self._window.bind("<Escape>", lambda _event: self.hide())
		self._window.bind("<FocusOut>", lambda _event: self.hide())

		self._canvas = tk.Canvas(
			self._window,
			background=SURFACE_BASE,
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
		width = self._unit(PAD_X + CHECK_COLUMN + TRAILING_PAD) + widest
		height = self._unit(PAD_Y) * 2
		for row in rows:
			height += self._unit(SEPARATOR_HEIGHT if row.key == SEPARATOR else ROW_HEIGHT)
		return int(round(width)), int(round(height))

	def _draw(self, width: int) -> None:
		"""Draw every row, and the highlight that will track the pointer.

		Args:
			width: Width of the menu in device pixels. int.

		Returns:
			None.
		"""
		self._canvas.delete("all")
		self._row_tops = []

		inset = self._unit(PAD_X) / 2.0
		self._highlight_photo = ImageTk.PhotoImage(
			rounded_fill(
				int(round(width - inset * 2)),
				int(round(self._unit(ROW_HEIGHT))),
				mix_hex(SURFACE_BASE, LABEL_PRIMARY, HIGHLIGHT_OPACITY),
				self._unit(HIGHLIGHT_RADIUS),
			)
		)
		self._highlight_item = self._canvas.create_image(inset, 0, image=self._highlight_photo, anchor="nw", state="hidden")

		y = self._unit(PAD_Y)
		for row in self._rows:
			if row.key == SEPARATOR:
				middle = y + self._unit(SEPARATOR_HEIGHT) / 2.0
				self._canvas.create_line(
					self._unit(PAD_X),
					middle,
					width - self._unit(PAD_X),
					middle,
					fill=mix_hex(SURFACE_BASE, LABEL_PRIMARY, SEPARATOR_OPACITY),
				)
				y += self._unit(SEPARATOR_HEIGHT)
				continue

			height = self._unit(ROW_HEIGHT)
			self._row_tops.append((y, y + height, row.key))
			if row.checked:
				self._canvas.create_text(
					self._unit(PAD_X + CHECK_COLUMN / 2.0),
					y + height / 2.0,
					text=CHECK_MARK,
					font=text_style("row"),
					fill=self._accent,
				)
			self._canvas.create_text(
				self._unit(PAD_X + CHECK_COLUMN),
				y + height / 2.0,
				text=row.label,
				font=text_style("row"),
				fill=LABEL_PRIMARY if row.checked else LABEL_SECONDARY,
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
				self._canvas.coords(self._highlight_item, self._unit(PAD_X) / 2.0, top)
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

	def show(self, rows: tuple[MenuRow, ...], pointer: tuple[int, int]) -> None:
		"""Draw the menu and open it at the pointer.

		The menu opens up and to the left of the pointer, the way a menu from the
		notification area does, and is pushed back inside the work area when that
		would take it off screen.

		Args:
			rows: The lines to draw, in order. tuple of MenuRow, non-empty.
			pointer: Where the pointer is as (x, y) in screen pixels. tuple of
				two ints.

		Returns:
			None.
		"""
		require_type(rows, tuple, "rows")
		if not rows:
			raise ValueError("rows must not be empty")

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
		apply_panel_chrome(self._window_handle())
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

