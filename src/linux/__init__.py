"""The Linux widget: its entry point, its backend, its tray, and its build.

Everything the Linux and Windows widgets share lives in src/common. What is
here is what only Linux does: speaking the StatusNotifierItem protocol for the
tray icons, asking the desktop for its theme, fonts and panel, writing the
XDG autostart entry, and packing it all into one executable. The KDE Plasma
widget under plasma/ reads the readings this writes.
"""
