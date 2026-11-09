"""The widgets FORL puts on the Windows desktop, in the look of the Mac app's.

Each widget is a borderless window that Windows draws from one picture with an
alpha channel, so its rounded corners and its type are smooth against the
desktop. It is kept out of the taskbar and Alt+Tab, at the bottom of the window
stack, never takes the focus when clicked, and is owned by the desktop window,
which is what keeps it on the desktop when Show desktop hides every other
window. Its card is solid, in the colors of the system's light or dark mode or
in a color the user picked, with the text drawn light or dark to read on it, or
glass: the wallpaper behind it, blurred and tinted light or dark.

A widget sits above the desktop icons rather than behind them: a window behind
the icons never receives a click, and these are clicked, dragged and
right-clicked.

Dragging a widget moves it, and its place is kept. It stays whole on the
screens: it stops at an outer edge of a display and at the taskbar, and crosses
where one display meets another. A widget can snap to the desktop's icon grid,
moving from cell to cell as the icons do, or move freely. Right-clicking it
offers its provider, what it shows, its style, snapping, locking its position,
and its removal. Widgets are added from FORL's settings.
"""

from __future__ import annotations

import ctypes
import tkinter as tk
import uuid
from tkinter import colorchooser
from ctypes import wintypes
from typing import Any, Callable

from PIL import Image, ImageChops

from src.common.render.theme import DARK_PALETTE, LIGHT_PALETTE, Palette, contrast_ratio
from src.common.settings.store import load_desktop_widgets, save_desktop_widgets
from src.common.system import work_area
from src.common.ui.core import SEPARATOR, MenuRow, ProviderView
from src.common.ui.menu import TrayMenu
from src.common.ui.palette import current_palette
from src.common.validation import require_member, require_non_empty_str, require_type

from . import wallpaper
from .widget_render import MEDIUM, SIZES, SMALL, MAX_ROWS, average_color, card_palette, compose, default_usages, glass, render_content

GWL_EXSTYLE = -20
GWLP_HWNDPARENT = -8
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_APPWINDOW = 0x00040000
HWND_BOTTOM = 1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
ULW_ALPHA = 0x00000002
AC_SRC_ALPHA = 0x01
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMWCP_DONOTROUND = 1
DWMWA_COLOR_NONE = 0xFFFFFFFE

# How far the pointer moves before a press is a drag rather than a click, in pixels.
DRAG_THRESHOLD = 4
# The shortest time between two frames of a glass widget being dragged, in
# milliseconds. Each frame draws only the glass again; the widget's content is
# kept from the start of the drag.
GLASS_FRAME_MS = 16
# How long after a widget's menu closes it is sent to the bottom again, in
# milliseconds, for the focus that lands on the desktop after the menu has gone.
MENU_SETTLE_MS = 150
# Where a new widget goes, from the top right of the work area, and how far each
# next one steps along, in points.
NEW_WIDGET_MARGIN = 24
NEW_WIDGET_STEP = 24

REMOVE_KEY = "remove"
SERVICE_PREFIX = "service:"
USAGE_PREFIX = "usage:"
SERVICE_KEY = "menu:service"
SHOW_KEY = "menu:show"
STYLE_KEY = "menu:style"
POSITION_KEY = "menu:position"
GLASS_KEY = "menu:glass"
CUSTOM_KEY = "background:custom"
GLASS_LIGHT_KEY = "background:glass_light"
GLASS_DARK_KEY = "background:glass_dark"
SERVICE_LABEL = "Provider"
SHOW_LABEL = "Show"
STYLE_LABEL = "Style"
POSITION_LABEL = "Position"
GLASS_LABEL = "Glass"
CUSTOM_LABEL = "Custom color"
GLASS_LIGHT_LABEL = "Light"
GLASS_DARK_LABEL = "Dark"
SOLID_STYLE = "solid"
GLASS_TONES = {"glass_light": "light", "glass_dark": "dark"}
REMOVE_LABEL = "Remove widget"
LOCK_KEY = "lock"
LOCK_LABEL = "Lock position"
SNAP_KEY = "snap"
SNAP_LABEL = "Snap to grid"
# Asked of the desktop's icon view for the size of its grid: the reply carries
# the width in its low word and the height in its high word.
LVM_GETITEMSPACING = 0x1033
SMTO_ABORTIFHUNG = 0x0002
# The icon grid of the default medium icons at 96 dots per inch, used when the
# desktop cannot be asked.
DEFAULT_GRID = (75, 100)

_user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None
_gdi32 = ctypes.windll.gdi32 if hasattr(ctypes, "windll") else None
_dwmapi = ctypes.windll.dwmapi if hasattr(ctypes, "windll") else None


class _BitmapHeader(ctypes.Structure):
	_fields_ = [
		("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
		("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
		("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
		("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
	]


class _WindowPos(ctypes.Structure):
	_fields_ = [
		("hwnd", wintypes.HWND), ("hwndInsertAfter", wintypes.HWND), ("x", ctypes.c_int), ("y", ctypes.c_int),
		("cx", ctypes.c_int), ("cy", ctypes.c_int), ("flags", wintypes.UINT),
	]


# The window procedure a widget's window is given, which sees every change to
# its place in the stack before Windows makes it.
_WindowProc = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
GWLP_WNDPROC = -4
WM_WINDOWPOSCHANGING = 0x0046


class _BlendFunction(ctypes.Structure):
	_fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte), ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


def _declare() -> None:
	"""Give the Windows calls used here their argument and return types.

	Without them a handle wider than 32 bits would be cut short on its way in or
	out.

	Returns:
		None.
	"""
	_user32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.c_void_p, ctypes.c_void_p, wintypes.HDC, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
	_user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
	_user32.SetWindowLongPtrW.restype = ctypes.c_void_p
	_user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
	_user32.GetWindowLongPtrW.restype = ctypes.c_void_p
	_user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
	_user32.FindWindowW.restype = wintypes.HWND
	_user32.GetDC.restype = wintypes.HDC
	_user32.GetDC.argtypes = [wintypes.HWND]
	_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
	_user32.IsWindow.argtypes = [wintypes.HWND]
	_gdi32.CreateCompatibleDC.restype = wintypes.HDC
	_gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
	_gdi32.CreateDIBSection.restype = wintypes.HBITMAP
	_gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
	_gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
	_gdi32.SelectObject.restype = wintypes.HGDIOBJ
	_gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
	_gdi32.DeleteDC.argtypes = [wintypes.HDC]
	_user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
	_user32.FindWindowExW.restype = wintypes.HWND
	_user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM, wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
	_user32.SendMessageTimeoutW.restype = ctypes.c_size_t
	_user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
	_user32.CallWindowProcW.restype = ctypes.c_ssize_t
	_dwmapi.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]


if _user32 is not None:
	_declare()


def _desktop_window() -> int:
	"""Return the window that holds the desktop.

	Returns:
		int: The handle of Program Manager, or 0 when there is none, as while
		Explorer restarts.
	"""
	return _user32.FindWindowW("Progman", None) or 0


def _premultiplied(image: Image.Image) -> bytes:
	"""Return an image's pixels the way a layered window takes them.

	Args:
		image: The picture, mode "RGBA". PIL.Image.Image.

	Returns:
		bytes: Blue, green, red and alpha for each pixel, each color already
		multiplied by its alpha.
	"""
	red, green, blue, alpha = image.split()
	return Image.merge(
		"RGBA",
		(ImageChops.multiply(blue, alpha), ImageChops.multiply(green, alpha), ImageChops.multiply(red, alpha), alpha),
	).tobytes()


class _WidgetWindow:
	"""One borderless window drawn from a picture, pinned to the desktop."""

	def __init__(self, master: tk.Tk) -> None:
		"""Create the window, hidden, and give it the styles of a desktop widget.

		Args:
			master: The application root window. tkinter.Tk.

		Returns:
			None.
		"""
		require_type(master, tk.Tk, "master")
		self.window = tk.Toplevel(master)
		self.window.withdraw()
		self.window.overrideredirect(True)
		self.window.title("FORL widget")
		self.window.update_idletasks()
		frame = self.window.frame()
		self.handle = int(frame, 16) if frame else self.window.winfo_id()
		self._owner = 0
		self._position = (0, 0)
		self._size = (0, 0)
		style = _user32.GetWindowLongW(self.handle, GWL_EXSTYLE)
		style = (style | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW
		_user32.SetWindowLongW(self.handle, GWL_EXSTYLE, style)
		# A drawn picture has no border of its own; the one Windows draws round
		# a window would sit outside the solid card's rounded corners.
		color = ctypes.c_uint(DWMWA_COLOR_NONE)
		_dwmapi.DwmSetWindowAttribute(self.handle, DWMWA_BORDER_COLOR, ctypes.byref(color), ctypes.sizeof(color))
		# The card draws its own rounded corners, which Windows must not clip to its own.
		corner = ctypes.c_int(DWMWCP_DONOTROUND)
		_dwmapi.DwmSetWindowAttribute(self.handle, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(corner), ctypes.sizeof(corner))
		# Windows raises a window for reasons of its own: with the desktop that
		# owns it when the desktop is activated, as it is at every sign-in and
		# when a menu closes. Every change to the window's place in the stack
		# is caught before it is made and turned into one to the bottom, so the
		# widget never comes up over another window, whatever asked.
		self._procedure = _WindowProc(self._on_message)
		self._previous_procedure = _user32.SetWindowLongPtrW(self.handle, GWLP_WNDPROC, ctypes.cast(self._procedure, ctypes.c_void_p))

	def _on_message(self, handle: int, message: int, wparam: int, lparam: int) -> int:
		"""Keep the window at the bottom of the stack, and pass every message on to Tk.

		Args:
			handle: The window. int.
			message: The message. int.
			wparam: Its first parameter. int.
			lparam: Its second parameter. int.

		Returns:
			int: What Tk's own procedure answers.
		"""
		if message == WM_WINDOWPOSCHANGING and lparam:
			position = ctypes.cast(lparam, ctypes.POINTER(_WindowPos)).contents
			if not position.flags & SWP_NOZORDER:
				position.hwndInsertAfter = HWND_BOTTOM
		return _user32.CallWindowProcW(self._previous_procedure, handle, message, wparam, lparam)

	def pin(self, force: bool = False) -> None:
		"""Hand the window to the desktop and put it at the bottom of the stack.

		Done when the window first appears, when the desktop window has changed,
		as after Explorer restarts, and when a dragged widget is dropped. Not at
		every redraw: two overlapping widgets each sent to the bottom in turn
		would swap places at every frame and flicker.

		Args:
			force: Whether to put it at the bottom even though the desktop window
				has not changed. bool.

		Returns:
			None.
		"""
		require_type(force, bool, "force")
		owner = _desktop_window()
		changed = bool(owner) and owner != self._owner and bool(_user32.IsWindow(owner))
		if changed:
			_user32.SetWindowLongPtrW(self.handle, GWLP_HWNDPARENT, owner)
			self._owner = owner
		if changed or force:
			_user32.SetWindowPos(self.handle, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)

	def draw(self, image: Image.Image, position: tuple[int, int]) -> None:
		"""Show a picture as the window, at a place on the screen.

		Args:
			image: The widget, mode "RGBA". PIL.Image.Image.
			position: Its top left corner, in screen pixels. tuple of two ints.

		Returns:
			None.
		"""
		require_type(image, Image.Image, "image")
		width, height = image.size
		if self._size != (width, height) or self._position != position:
			# Tk is told the window's size and place as well, so the events it
			# reports are measured against the window as drawn.
			self.window.geometry(f"{width}x{height}+{position[0]}+{position[1]}")
		self.window.deiconify()
		screen = _user32.GetDC(None)
		memory = _gdi32.CreateCompatibleDC(screen)
		bits = ctypes.c_void_p()
		header = _BitmapHeader(ctypes.sizeof(_BitmapHeader), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
		bitmap = _gdi32.CreateDIBSection(screen, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
		try:
			ctypes.memmove(bits, _premultiplied(image), width * height * 4)
			previous = _gdi32.SelectObject(memory, bitmap)
			destination = wintypes.POINT(*position)
			size = wintypes.SIZE(width, height)
			source = wintypes.POINT(0, 0)
			blend = _BlendFunction(0, 0, 255, AC_SRC_ALPHA)
			_user32.UpdateLayeredWindow(self.handle, screen, ctypes.byref(destination), ctypes.byref(size), memory, ctypes.byref(source), 0, ctypes.byref(blend), ULW_ALPHA)
			_gdi32.SelectObject(memory, previous)
		finally:
			_gdi32.DeleteObject(bitmap)
			_gdi32.DeleteDC(memory)
			_user32.ReleaseDC(None, screen)
		self._size = (width, height)
		self._position = position
		self.pin()

	def move(self, position: tuple[int, int]) -> None:
		"""Move the window without drawing it again.

		Args:
			position: Its new top left corner, in screen pixels. tuple of two ints.

		Returns:
			None.
		"""
		_user32.SetWindowPos(self.handle, None, position[0], position[1], 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
		self._position = position

	def destroy(self) -> None:
		"""Close the window, giving it back its own window procedure first.

		Returns:
			None.
		"""
		if self._previous_procedure:
			_user32.SetWindowLongPtrW(self.handle, GWLP_WNDPROC, self._previous_procedure)
			self._previous_procedure = None
		self.window.destroy()


class DesktopWidgets:
	"""Every desktop widget the user placed: their windows, their menu and their storage."""

	def __init__(
		self,
		master: tk.Tk,
		keys: tuple[str, ...],
		describe: Callable[[str], ProviderView],
	) -> None:
		"""Read the stored widgets without showing them yet.

		Args:
			master: The application root window. tkinter.Tk.
			keys: Every service, in the order the menu lists them. tuple of str,
				non-empty.
			describe: Returns everything known about one service, given its key.
				Callable taking one str and returning ProviderView.

		Returns:
			None.
		"""
		require_type(master, tk.Tk, "master")
		require_type(keys, tuple, "keys")
		if not keys:
			raise ValueError("keys must not be empty")
		if not callable(describe):
			raise TypeError("describe must be callable")
		self._master = master
		self._keys = keys
		self._describe = describe
		self._items = [item for item in load_desktop_widgets() if item["service"] in keys]
		self._windows: dict[str, _WidgetWindow] = {}
		self._menu = TrayMenu(master, on_choose=self._choose, on_close=self._after_menu)
		self._menu_target = ""
		self._press: tuple[int, int, int, int] | None = None
		# A glass widget being dragged: its content, drawn once at the start, the
		# palette it was drawn in, and whether a frame is waiting to be drawn.
		self._drag_content: tuple[Image.Image, Palette] | None = None
		self._frame_job: str | None = None
		self._dragged = False
		self._started = False

	def _scale(self) -> float:
		"""Return the display's pixels per point.

		Returns:
			float: The scale, 1 at 96 dots per inch.
		"""
		return self._master.winfo_fpixels("1i") / 96.0

	def _item(self, identifier: str) -> dict[str, Any] | None:
		"""Return one widget's stored description.

		Args:
			identifier: The widget's id. str.

		Returns:
			dict or None: The widget, or None when it has been removed.
		"""
		return next((item for item in self._items if item["id"] == identifier), None)

	def _save(self) -> None:
		"""Write every widget's description to the preferences file.

		Returns:
			None.
		"""
		save_desktop_widgets(self._items)

	def _place_new(self, size: str) -> tuple[int, int]:
		"""Return where a new widget goes: the top right of the screen, stepped along.

		Args:
			size: SMALL or MEDIUM. str.

		Returns:
			tuple: Its top left corner, in screen pixels.
		"""
		scale = self._scale()
		left, top, right, _bottom = work_area(self._master.winfo_screenwidth(), self._master.winfo_screenheight())
		step = int(NEW_WIDGET_STEP * scale) * len(self._items)
		width = int(SIZES[size][0] * scale)
		margin = int(NEW_WIDGET_MARGIN * scale)
		return (max(left, right - width - margin - step), top + margin + step)

	def add(self, service: str, size: str) -> None:
		"""Add a widget of a size, showing a service.

		Args:
			service: Key of the service it shows, the one of the settings tab it
				was added from. str, one of the keys the widgets were built with.
			size: SMALL or MEDIUM. str.

		Returns:
			None.
		"""
		require_member(service, frozenset(self._keys), "service")
		require_member(size, frozenset(SIZES), "size")
		x, y = self._place_new(size)
		self._items.append({
			"id": uuid.uuid4().hex,
			"size": size,
			"service": service,
			"usages": default_usages(size),
			# Glass in the tone of the system's mode, as a Mac widget starts out.
			"style": "glass_dark" if current_palette().dark else "glass_light",
			"locked": False,
			"snap": False,
			"color": None,
			"x": x,
			"y": y,
		})
		self._save()
		if self._started:
			self.refresh()

	def start(self) -> None:
		"""Show every stored widget.

		Returns:
			None.
		"""
		self._started = True
		self.refresh()

	def refresh(self) -> None:
		"""Draw every widget again, from the readings and the system's mode as they are now.

		Returns:
			None.
		"""
		if not self._started:
			return
		palette = current_palette()
		scale = self._scale()
		wanted = {item["id"] for item in self._items}
		for identifier in [key for key in self._windows if key not in wanted]:
			self._windows.pop(identifier).destroy()
		for item in self._items:
			window = self._windows.get(item["id"])
			if window is None:
				window = self._create(item["id"])
			self._draw(window, item, palette, scale)

	def _create(self, identifier: str) -> _WidgetWindow:
		"""Create one widget's window and attach its mouse handling.

		Args:
			identifier: The widget's id. str.

		Returns:
			_WidgetWindow: The window, not yet drawn.
		"""
		window = _WidgetWindow(self._master)
		window.window.bind("<ButtonPress-1>", lambda event: self._on_press(identifier, event))
		window.window.bind("<B1-Motion>", lambda event: self._on_drag(identifier, event))
		window.window.bind("<ButtonRelease-1>", lambda event: self._on_release(identifier, event))
		window.window.bind("<ButtonRelease-3>", lambda event: self._open_menu(identifier, event))
		self._windows[identifier] = window
		return window

	def _draw(self, window: _WidgetWindow, item: dict[str, Any], palette: Palette, scale: float) -> None:
		"""Draw one widget.

		Args:
			window: Its window. _WidgetWindow.
			item: Its description. dict.
			palette: The colors of the system's mode. Palette.
			scale: The display's pixels per point. float.

		Returns:
			None.
		"""
		if item["x"] is None or item["y"] is None:
			item["x"], item["y"] = self._place_new(item["size"])
		# A display may have been removed or rearranged since the widget was placed.
		item["x"], item["y"] = self._on_screens(item, (item["x"], item["y"]), None)
		surface = self._glass(item, scale)
		widget_palette = self._widget_palette(item, palette, surface)
		content = render_content(item["size"], self._describe(item["service"]), item["usages"], widget_palette, scale)
		window.draw(compose(content, widget_palette, scale, surface), (item["x"], item["y"]))

	def _widget_palette(self, item: dict[str, Any], palette: Palette, surface: Image.Image | None) -> Palette:
		"""Return the colors one widget is drawn in.

		Args:
			item: The widget. dict.
			palette: The colors of the system's mode. Palette.
			surface: Its glass, or None for a solid widget. PIL.Image.Image or None.

		Returns:
			Palette: For glass, the tone's text over the glass's average color;
			otherwise the solid card's colors.
		"""
		if surface is None:
			return self._palette_for(item, palette)
		base = DARK_PALETTE if GLASS_TONES[item["style"]] == "dark" else LIGHT_PALETTE
		return card_palette(base, average_color(surface))

	def _glass(self, item: dict[str, Any], scale: float) -> Image.Image | None:
		"""Return a glass widget's glass, from the wallpaper behind it where it is now.

		Args:
			item: The widget. dict.
			scale: The display's pixels per point. float.

		Returns:
			PIL.Image.Image or None: The glass, or None for a solid widget or when
			the wallpaper cannot be read, which draws the widget solid.
		"""
		tone = GLASS_TONES.get(item["style"])
		if tone is None:
			return None
		width, height = (int(round(value * scale)) for value in SIZES[item["size"]])
		backdrop = wallpaper.behind(item["x"], item["y"], width, height)
		return glass(backdrop, tone, scale) if backdrop is not None else None

	@staticmethod
	def _palette_for(item: dict[str, Any], system: Palette) -> Palette:
		"""Return the colors a widget is drawn in.

		Args:
			item: The widget. dict.
			system: The colors of the system's light or dark mode. Palette.

		Returns:
			Palette: The system's colors, or for a custom background, whichever
			of the light and dark text contrasts more with it, with the
			background as the surface.
		"""
		color = item["color"]
		if color is None:
			return system
		light_text = contrast_ratio(DARK_PALETTE.label_primary, color) >= contrast_ratio(LIGHT_PALETTE.label_primary, color)
		return card_palette(DARK_PALETTE if light_text else LIGHT_PALETTE, color)

	def _on_press(self, identifier: str, event: tk.Event) -> None:
		"""Remember where a press began, which a drag is measured from.

		Args:
			identifier: The widget pressed. str.
			event: The press. tkinter.Event.

		Returns:
			None.
		"""
		item = self._item(identifier)
		if item is None:
			return
		self._press = (event.x_root, event.y_root, item["x"], item["y"])
		self._dragged = False

	def _on_drag(self, identifier: str, event: tk.Event) -> None:
		"""Move a widget with the pointer, once the pointer has gone past the threshold.

		Args:
			identifier: The widget dragged. str.
			event: The motion. tkinter.Event.

		Returns:
			None.
		"""
		item = self._item(identifier)
		if item is None or self._press is None or item["locked"]:
			return
		start_x, start_y, left, top = self._press
		dx, dy = event.x_root - start_x, event.y_root - start_y
		if not self._dragged and abs(dx) < DRAG_THRESHOLD and abs(dy) < DRAG_THRESHOLD:
			return
		if not self._dragged and item["style"] != SOLID_STYLE:
			# The content does not change during a drag, so it is drawn once now
			# and laid on new glass at every frame.
			scale = self._scale()
			surface = self._glass(item, scale)
			palette = self._widget_palette(item, current_palette(), surface)
			self._drag_content = (render_content(item["size"], self._describe(item["service"]), item["usages"], palette, scale), palette)
		self._dragged = True
		wanted = self._snapped((left + dx, top + dy)) if item["snap"] else (left + dx, top + dy)
		item["x"], item["y"] = self._on_screens(item, wanted, (event.x_root, event.y_root))
		if item["style"] == SOLID_STYLE:
			self._windows[identifier].move((item["x"], item["y"]))
		elif self._frame_job is None:
			# Frames are drawn at most every GLASS_FRAME_MS, at the latest place,
			# so a fast pointer is never queued behind its own trail.
			self._frame_job = self._master.after(GLASS_FRAME_MS, lambda: self._glass_frame(identifier))

	def _on_screens(self, item: dict[str, Any], wanted: tuple[int, int], pointer: tuple[int, int] | None) -> tuple[int, int]:
		"""Return the nearest place to a wanted one where a widget lies whole on the screens.

		A widget may lie across two displays where they meet, so it crosses from
		one to the other; where no display goes on, it stops at the edge, and it
		never goes under the taskbar.

		Args:
			item: The widget. dict.
			wanted: Where it would go, its top left corner in screen pixels.
				tuple of two ints.
			pointer: Where the pointer is during a drag, whose display it is kept
				on when it cannot go where wanted, or None to use the display
				nearest the widget. tuple of two ints, or None.

		Returns:
			tuple: The place, in screen pixels.
		"""
		areas = [work for _whole, work in wallpaper.displays()]
		if not areas:
			return wanted
		scale = self._scale()
		width, height = (int(round(value * scale)) for value in SIZES[item["size"]])
		x, y = wanted

		def covered(px: int, py: int) -> bool:
			if any(area[0] <= px < area[2] and area[1] <= py < area[3] for area in areas):
				return True
			# Displays scaled differently can be reported with a gap between them
			# where they meet; a point in such a gap is on the seam, not off the
			# screens.
			for first in areas:
				for second in areas:
					across = first[2] <= px < second[0] and first[1] <= py < first[3] and second[1] <= py < second[3]
					down = first[3] <= py < second[1] and first[0] <= px < first[2] and second[0] <= px < second[2]
					if across or down:
						return True
			return False

		probes = [(x + dx, y + dy) for dx in (0, width // 2, width - 1) for dy in (0, height // 2, height - 1)]
		if all(covered(px, py) for px, py in probes):
			return wanted
		anchor = pointer or (x + width // 2, y + height // 2)
		area = next((area for area in areas if area[0] <= anchor[0] < area[2] and area[1] <= anchor[1] < area[3]), None)
		if area is None:
			area = min(areas, key=lambda candidate: abs((candidate[0] + candidate[2]) / 2 - anchor[0]) + abs((candidate[1] + candidate[3]) / 2 - anchor[1]))
		return (min(max(x, area[0]), area[2] - width), min(max(y, area[1]), area[3] - height))

	def _grid(self) -> tuple[int, int]:
		"""Return the size of a cell of the desktop's icon grid.

		Returns:
			tuple: Its width and height in pixels, asked of the desktop's icon
			view, or the default grid scaled to the display when it cannot be.
		"""
		view = 0
		for parent_class in ("Progman", "WorkerW"):
			parent = _user32.FindWindowExW(None, None, parent_class, None)
			while parent and not view:
				shell = _user32.FindWindowExW(parent, None, "SHELLDLL_DefView", None)
				if shell:
					view = _user32.FindWindowExW(shell, None, "SysListView32", None)
				parent = _user32.FindWindowExW(None, parent, parent_class, None)
			if view:
				break
		if view:
			reply = ctypes.c_size_t()
			if _user32.SendMessageTimeoutW(view, LVM_GETITEMSPACING, 0, 0, SMTO_ABORTIFHUNG, 200, ctypes.byref(reply)):
				width, height = reply.value & 0xFFFF, (reply.value >> 16) & 0xFFFF
				if width > 0 and height > 0:
					return (width, height)
		scale = self._scale()
		return (int(round(DEFAULT_GRID[0] * scale)), int(round(DEFAULT_GRID[1] * scale)))

	def _snapped(self, position: tuple[int, int]) -> tuple[int, int]:
		"""Return the corner of the icon grid cell nearest a place.

		The grid starts at the top left of the work area of the display the
		place is on, as the icons' does.

		Args:
			position: The place, in screen pixels. tuple of two ints.

		Returns:
			tuple: The nearest cell's top left corner, in screen pixels.
		"""
		areas = [work for _whole, work in wallpaper.displays()]
		area = next((area for area in areas if area[0] <= position[0] < area[2] and area[1] <= position[1] < area[3]), areas[0] if areas else (0, 0, 0, 0))
		cell_width, cell_height = self._grid()
		x = area[0] + round((position[0] - area[0]) / cell_width) * cell_width
		y = area[1] + round((position[1] - area[1]) / cell_height) * cell_height
		return (x, y)

	def _glass_frame(self, identifier: str) -> None:
		"""Draw a dragged glass widget where it now is, on the glass behind it there.

		Args:
			identifier: The widget. str.

		Returns:
			None.
		"""
		self._frame_job = None
		item = self._item(identifier)
		window = self._windows.get(identifier)
		if item is None or window is None or self._drag_content is None:
			return
		scale = self._scale()
		surface = self._glass(item, scale)
		content, palette = self._drag_content
		window.draw(compose(content, palette, scale, surface), (item["x"], item["y"]))

	def _on_release(self, identifier: str, event: tk.Event) -> None:
		"""Keep a moved widget's place.

		A click that does not move the widget does nothing, as on the Mac desktop.

		Args:
			identifier: The widget released. str.
			event: The release. tkinter.Event.

		Returns:
			None.
		"""
		item = self._item(identifier)
		self._press = None
		if item is None:
			return
		if self._dragged:
			self._dragged = False
			self._save()
			if self._frame_job is not None:
				self._master.after_cancel(self._frame_job)
				self._frame_job = None
			self._drag_content = None
			if item["style"] != SOLID_STYLE:
				# Drawn whole once more, so the text takes the colors that read
				# best on the glass where the widget came to rest.
				self._redraw(identifier)
			self._windows[identifier].pin(force=True)

	def _redraw(self, identifier: str) -> None:
		"""Draw one widget again, where it now is.

		Args:
			identifier: The widget. str.

		Returns:
			None.
		"""
		item = self._item(identifier)
		window = self._windows.get(identifier)
		if item is not None and window is not None:
			self._draw(window, item, current_palette(), self._scale())

	def _menus(self, item: dict[str, Any]) -> tuple[tuple[MenuRow, ...], dict[str, tuple[MenuRow, ...]]]:
		"""Return a widget's right-click menu and its submenus.

		Args:
			item: The widget. dict.

		Returns:
			tuple: The menu's rows, which are Provider, Show, Style and Position,
			each opening a submenu, then removal; and the submenus by the key of the
			row that opens them: the services, the usages of the widget's
			service, the styles, whose Glass row opens its light and dark tints,
			and the position's snapping to the grid and locking.
		"""
		services = tuple(MenuRow(f"{SERVICE_PREFIX}{key}", self._describe(key).provider.label, key == item["service"], True) for key in self._keys)
		snapshot = self._describe(item["service"]).snapshot
		metrics = snapshot.metrics() if snapshot is not None else ()
		choices = [(metric.key, metric.label) for metric in metrics] or [(key, key.title()) for key in default_usages(MEDIUM)]
		# A small widget shows one usage, so its list is marked as a choice of
		# one; a medium one shows several, which are ticked.
		single = item["size"] == SMALL
		usages = tuple(MenuRow(f"{USAGE_PREFIX}{key}", label, key in item["usages"][:1 if single else None], single) for key, label in choices)
		styles = (
			MenuRow(GLASS_KEY, GLASS_LABEL, item["style"] != SOLID_STYLE, True),
			MenuRow(CUSTOM_KEY, CUSTOM_LABEL, item["style"] == SOLID_STYLE, True),
		)
		tints = (
			MenuRow(GLASS_LIGHT_KEY, GLASS_LIGHT_LABEL, item["style"] == "glass_light", True),
			MenuRow(GLASS_DARK_KEY, GLASS_DARK_LABEL, item["style"] == "glass_dark", True),
		)
		rows = (
			MenuRow(SERVICE_KEY, SERVICE_LABEL, False),
			MenuRow(SHOW_KEY, SHOW_LABEL, False),
			MenuRow(STYLE_KEY, STYLE_LABEL, False),
			MenuRow(POSITION_KEY, POSITION_LABEL, False),
			MenuRow(SEPARATOR, "", False),
			MenuRow(REMOVE_KEY, REMOVE_LABEL, False),
		)
		position = (
			MenuRow(SNAP_KEY, SNAP_LABEL, item["snap"]),
			MenuRow(LOCK_KEY, LOCK_LABEL, item["locked"]),
		)
		return rows, {SERVICE_KEY: services, SHOW_KEY: usages, STYLE_KEY: styles, POSITION_KEY: position, GLASS_KEY: tints}

	def _open_menu(self, identifier: str, event: tk.Event) -> None:
		"""Open a widget's right-click menu at the pointer.

		Args:
			identifier: The widget right-clicked. str.
			event: The click. tkinter.Event.

		Returns:
			None.
		"""
		item = self._item(identifier)
		if item is None:
			return
		self._menu_target = identifier
		accent = self._describe(item["service"]).provider.accent
		rows, submenus = self._menus(item)
		self._menu.show(rows, (event.x_root, event.y_root), accent, submenus=submenus)

	def _after_menu(self) -> None:
		"""Put every widget back at the bottom once its menu has closed.

		Closing the menu hands the focus back to the desktop, and Windows raises
		the windows the desktop owns with it, which the widgets are: left
		alone, a widget would come up over the windows it was under. It is sent
		down at once and again a moment later, since the focus can land after
		the menu has gone.

		Returns:
			None.
		"""
		for delay in (0, MENU_SETTLE_MS):
			self._master.after(delay, self._send_down)

	def _send_down(self) -> None:
		"""Put every widget at the bottom of the window stack.

		Returns:
			None.
		"""
		for window in self._windows.values():
			window.pin(force=True)

	def _choose(self, key: str) -> None:
		"""Act on a line chosen from a widget's menu.

		A small widget shows one usage, so choosing one replaces it; a medium
		widget shows several, so choosing one adds or removes it, up to as many
		as it has room for.

		Args:
			key: The chosen line's key. str, non-empty.

		Returns:
			None.
		"""
		require_non_empty_str(key, "key")
		item = self._item(self._menu_target)
		if item is None:
			return
		if key == REMOVE_KEY:
			self._items.remove(item)
		elif key == LOCK_KEY:
			item["locked"] = not item["locked"]
		elif key == SNAP_KEY:
			item["snap"] = not item["snap"]
			if item["snap"] and item["x"] is not None and item["y"] is not None:
				item["x"], item["y"] = self._on_screens(item, self._snapped((item["x"], item["y"])), None)
		elif key.startswith(SERVICE_PREFIX):
			service = key[len(SERVICE_PREFIX):]
			if service != item["service"]:
				item["service"] = service
				item["usages"] = default_usages(item["size"])
		elif key.startswith(USAGE_PREFIX):
			usage = key[len(USAGE_PREFIX):]
			if item["size"] == SMALL:
				item["usages"] = [usage]
			elif usage in item["usages"]:
				item["usages"] = [other for other in item["usages"] if other != usage]
			elif len(item["usages"]) < MAX_ROWS:
				item["usages"] = item["usages"] + [usage]
		elif key in (GLASS_LIGHT_KEY, GLASS_DARK_KEY):
			item["style"] = key.split(":", 1)[1]
		elif key == CUSTOM_KEY:
			_rgb, picked = colorchooser.askcolor(color=item["color"] or self._palette_for(item, current_palette()).surface, title="Widget background")
			if not picked:
				return
			item["style"] = SOLID_STYLE
			item["color"] = picked.lower()
		self._save()
		self.refresh()

	def stop(self) -> None:
		"""Close every widget's window.

		Returns:
			None.
		"""
		self._started = False
		self._menu.hide()
		for window in self._windows.values():
			window.destroy()
		self._windows.clear()
