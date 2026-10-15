"""Entry point of the Linux widget.

	./FORL

Everything but what Linux alone does lives in src/common and is shared with
the Windows widget; this installs the Linux backend and starts it. The widget
puts its icons in the desktop's tray, writes its readings where status bars and
the KDE Plasma widget and the GNOME Shell extension read them, installs that
widget on a Plasma desktop and that extension on a GNOME one, and on a desktop
with no tray opens its panel as an ordinary window instead.

The interface is drawn with Tk, which speaks X11. Every desktop that runs on
Wayland also runs X11 programs through XWayland, so this needs nothing extra;
a session with no X display at all is refused with a message saying so.

Build the single executable with build.py.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
	sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

UNSUPPORTED_STATUS = 2


def main() -> int:
	"""Run the widget until the user quits it.

	Returns:
		int: Process exit status, 0 on a clean exit, 1 when the widget was
		already running in another process, and 2 on a machine that is not
		Linux or has no display to draw on.
	"""
	if not sys.platform.startswith("linux"):
		print("This is the Linux widget; Windows runs src/windows/main.py.", file=sys.stderr)
		return UNSUPPORTED_STATUS
	if not os.environ.get("DISPLAY"):
		print("FORL needs an X11 display; on Wayland, XWayland provides one.", file=sys.stderr)
		return UNSUPPORTED_STATUS
	from src.common import launcher
	from src.linux import backend

	backend.install_plasma_widget()
	backend.install_gnome_extension()
	backend.install_bus_service()
	return launcher.run(backend)


if __name__ == "__main__":
	raise SystemExit(main())
