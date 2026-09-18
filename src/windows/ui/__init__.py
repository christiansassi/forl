"""User interface.

What the widget does, as opposed to how it looks, lives in core.py and serves
both platforms: the poller, the sign-in, which usages the user chose, and the
preferences behind all of it. A platform gives the core a way to reach its own
thread and a way to be told something changed, and takes the rest.

Around that core sits the Windows interface: the notification area icons, the
menu drawn in place of the shell's own, the panel they open, and the drawing and
motion those are built from.

macOS has an application of its own, written in Swift and built from the mac
directory. It reads the same endpoints and shows the same numbers, but it is a
real application with real widgets rather than a second copy of this one, so
nothing here is shared with it beyond the shape of the reading.
"""
