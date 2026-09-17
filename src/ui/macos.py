"""The macOS widget.

Empty for now. The entry point picks this over the Windows widget by platform,
so the shape of the launch is already in place and what is missing is only what
appears on screen.

Three surfaces are planned, and the reading behind all three is the same
UsageSnapshot the Windows widget draws, taken by the same poller from the same
providers. Nothing under src/providers or src/usage needs a line changing.

	menu bar   the closest thing to what Windows has: one item per selected
	           usage, drawn by render_icon at the size the system backend
	           reports, opening the same panel on a click
	Dock       a badge on the application icon carrying the one reading the
	           user cares most about, there being room for only one
	desktop    a window at the desktop window level, sized by its own layout
	           rather than by the notification area, which is the one surface
	           with room for every usage at once

The panel, the menu and the settings in src/ui are drawn on a Tk canvas and are
not tied to Windows, so the menu bar surface should be able to open them
unchanged. The Dock badge and the desktop widget want layouts of their own.
"""

from __future__ import annotations

import sys

from ..providers import Provider
from ..validation import require_type

NOT_BUILT_STATUS = 3


def run_widget(provider: Provider) -> int:
	"""Run the macOS widget until the user quits it.

	Args:
		provider: The service to report on. Provider.

	Returns:
		int: Process exit status, NOT_BUILT_STATUS until there is something to
		run.
	"""
	require_type(provider, Provider, "provider")
	print(f"The macOS widget is not built yet, so {provider.label} usage cannot be shown.", file=sys.stderr)
	return NOT_BUILT_STATUS
