"""What the Windows and Linux widgets share, and the artwork every platform shares.

Everything that is the same on both desktops lives here: the sign-in, the
providers and their readings, the preferences, the drawing, the panel and the
logic behind it. Each platform keeps only what its system alone does, under
src/windows and src/linux, and installs it through the system package before
the widget starts. assets/ holds the marks and the icon, which the macOS app
uses as well.
"""
