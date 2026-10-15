"""User interface.

What the widget does, as opposed to how it looks, lives in core.py and serves
both platforms: the poller, the sign-in, which usages the user chose, and the
preferences behind all of it. A platform gives the core a way to reach its own
thread and a way to be told something changed, and takes the rest.

Around that core sits the desktop interface Windows and Linux share: the panel
the tray icons open, the menu drawn in place of the shell's own, the files
status bars and widgets read, and the drawing and motion those are built from.
The tray icons themselves are each platform's own, under src/windows and
src/linux.

macOS has an application of its own, written in Swift and built from the mac
directory. It reads the same endpoints and shows the same numbers, but it is a
real application with real widgets rather than a second copy of this one, so
nothing here is shared with it beyond the shape of the reading.
"""
