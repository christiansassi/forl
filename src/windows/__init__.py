"""The Windows widget: its entry point, its backend, its tray, and its build.

Everything the Windows and Linux widgets share lives in src/common. What is
here is what only Windows does: the notification area icons, the registry
entry that starts the widget at sign-in, the desktop window manager calls that
round the panel, and the build of the executable.
"""
