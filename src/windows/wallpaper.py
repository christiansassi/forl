"""The piece of the desktop wallpaper behind a widget, for its glass background.

Windows will not blur what is behind a window drawn from a picture with an alpha
channel, which is what the widgets are. A desktop widget only ever has the
wallpaper behind it, though, so its glass is made the way a frosted panel is
faked in a screenshot: the wallpaper is read from the file Windows draws it
from, laid out on each display the way Windows lays it out, and the part
behind the widget is cut out for the widget to blur and tint.

The wallpaper is read again only when its file, its layout or the displays have
changed, so a widget redrawn every minute costs one crop and one blur.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageOps

from src.common.validation import require_type

# The copy of the wallpaper Windows itself draws from, which exists even when the
# picture the user chose has since been moved or deleted.
TRANSCODED = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Themes" / "TranscodedWallpaper"
DESKTOP_KEY = r"Control Panel\Desktop"
COLORS_KEY = r"Control Panel\Colors"

# WallpaperStyle values, with TileWallpaper telling Center from Tile.
FILL = "10"
FIT = "6"
STRETCH = "2"
CENTER = "0"
SPAN = "22"

MONITORINFO_SIZE = 40

_cache: dict[str, object] = {"key": None, "screens": []}


class _MonitorInfo(ctypes.Structure):
	_fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


def _registry(path: str, name: str) -> str:
	"""Return one value of the current user's registry, as text.

	Args:
		path: The key under HKEY_CURRENT_USER. str.
		name: The value. str.

	Returns:
		str: The value, or an empty string when it is missing.
	"""
	import winreg

	try:
		with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
			return str(winreg.QueryValueEx(key, name)[0])
	except OSError:
		return ""


def displays() -> list[tuple[tuple[int, int, int, int], tuple[int, int, int, int]]]:
	"""Return every display's rectangle and the part of it the taskbar leaves free.

	Returns:
		list of tuple: (whole display, work area) for each display, each as
		(left, top, right, bottom) in screen pixels.
	"""
	found: list[tuple[tuple[int, int, int, int], tuple[int, int, int, int]]] = []
	callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

	def collect(monitor: int, _dc: int, _rect: object, _data: int) -> bool:
		info = _MonitorInfo()
		info.cbSize = ctypes.sizeof(_MonitorInfo)
		if ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
			whole, work = info.rcMonitor, info.rcWork
			found.append(((whole.left, whole.top, whole.right, whole.bottom), (work.left, work.top, work.right, work.bottom)))
		return True

	ctypes.windll.user32.EnumDisplayMonitors(None, None, callback_type(collect), 0)
	return found


def _background_color() -> tuple[int, int, int]:
	"""Return the desktop's background color, which shows where no picture does.

	Returns:
		tuple: Red, green and blue.
	"""
	parts = _registry(COLORS_KEY, "Background").split()
	try:
		red, green, blue = (int(part) for part in parts[:3])
		return (red, green, blue)
	except ValueError:
		return (0, 0, 0)


def _layout(picture: Image.Image | None, size: tuple[int, int], style: str, tiled: bool, color: tuple[int, int, int]) -> Image.Image:
	"""Return the wallpaper as Windows lays it out on an area of one size.

	Args:
		picture: The wallpaper, or None for a plain color. PIL.Image.Image or None.
		size: The area, in pixels. tuple of two ints.
		style: The WallpaperStyle value. str.
		tiled: Whether the picture is tiled. bool.
		color: The desktop's background color. tuple.

	Returns:
		PIL.Image.Image: The area as it looks, mode "RGB".
	"""
	canvas = Image.new("RGB", size, color)
	if picture is None:
		return canvas
	if style == STRETCH:
		return picture.resize(size, Image.LANCZOS)
	if style == FIT:
		fitted = ImageOps.contain(picture, size, Image.LANCZOS)
		canvas.paste(fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
		return canvas
	if style == CENTER and tiled:
		for x in range(0, size[0], picture.width):
			for y in range(0, size[1], picture.height):
				canvas.paste(picture, (x, y))
		return canvas
	if style == CENTER:
		canvas.paste(picture, ((size[0] - picture.width) // 2, (size[1] - picture.height) // 2))
		return canvas
	return ImageOps.fit(picture, size, Image.LANCZOS)


def _screens() -> list[tuple[tuple[int, int, int, int], Image.Image]]:
	"""Return each display with the wallpaper laid out on it, read again only when something changed.

	Returns:
		list: (display rectangle, wallpaper as laid out on it) for each display.
	"""
	path = TRANSCODED if TRANSCODED.is_file() else Path(_registry(DESKTOP_KEY, "WallPaper"))
	try:
		stamp = path.stat().st_mtime if str(path) and path.is_file() else 0.0
	except OSError:
		stamp = 0.0
	style = _registry(DESKTOP_KEY, "WallpaperStyle") or FILL
	tiled = _registry(DESKTOP_KEY, "TileWallpaper") == "1"
	monitors = [whole for whole, _work in displays()]
	key = (str(path), stamp, style, tiled, tuple(monitors))
	if _cache["key"] == key:
		return _cache["screens"]  # type: ignore[return-value]

	picture: Image.Image | None = None
	if stamp:
		try:
			with Image.open(path) as opened:
				picture = opened.convert("RGB")
		except OSError:
			picture = None
	color = _background_color()
	screens = []
	if style == SPAN and monitors:
		left = min(rect[0] for rect in monitors)
		top = min(rect[1] for rect in monitors)
		right = max(rect[2] for rect in monitors)
		bottom = max(rect[3] for rect in monitors)
		screens.append(((left, top, right, bottom), _layout(picture, (right - left, bottom - top), FILL, False, color)))
	else:
		for rect in monitors:
			screens.append((rect, _layout(picture, (rect[2] - rect[0], rect[3] - rect[1]), style, tiled, color)))
	_cache["key"] = key
	_cache["screens"] = screens
	return screens


def behind(left: int, top: int, width: int, height: int) -> Image.Image | None:
	"""Return the wallpaper behind a rectangle of the screen.

	Args:
		left: The rectangle's left edge, in screen pixels. int.
		top: Its top edge, in screen pixels. int.
		width: Its width, in pixels. int, greater than 0.
		height: Its height, in pixels. int, greater than 0.

	Returns:
		PIL.Image.Image or None: What the wallpaper shows there, mode "RGB",
		taken from the display holding the rectangle's center, or None when no
		display could be read.
	"""
	for value, name in ((left, "left"), (top, "top"), (width, "width"), (height, "height")):
		require_type(value, int, name)
	center = (left + width // 2, top + height // 2)
	screens = _screens()
	for rect, picture in screens:
		if rect[0] <= center[0] < rect[2] and rect[1] <= center[1] < rect[3]:
			box = (left - rect[0], top - rect[1], left - rect[0] + width, top - rect[1] + height)
			return picture.crop(box)
	return screens[0][1].crop((0, 0, width, height)) if screens else None
